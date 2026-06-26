"""
Risk Scoring Engine — the ONLY service that writes to canonical_scores.

This is the enforcement point of the Golden Source principle. Every risk score
in the platform originates here. No other service may write to canonical_scores.

What it produces per H3 cell per scoring run:
  score              — ensemble mean (0-100)
  risk_bucket        — LOW / MEDIUM / HIGH / VERY_HIGH
  ci_lower/ci_upper  — ensemble 10th/90th percentile (confidence band)
  score_velocity_*   — dScore/dt over 6h, 24h, 48h (the early warning signal)
  ensemble_scores    — per-model breakdown {xgb, lgbm, logistic}
  shap_factors       — XGBoost SHAP attribution (top factors for ECB/CSRD)
  compound_flag      — cross-hazard compound event active in this cell
  regulatory_fingerprint — SHA-256 of inputs; legally verifiable audit trail

Architecture:
  1. Load active model for hazard_type from model_registry
  2. Fetch ML features for target_date from ml_features_{hazard}
  3. Score via EnsembleScorer (XGBoost + LightGBM + Logistic)
  4. Compute velocity by comparing to prior canonical_scores
  5. Detect compound events via CompoundDetector
  6. Build regulatory fingerprint
  7. Write append-only rows to canonical_scores (valid_to IS NULL = current)
  8. Retire previous rows (set valid_to = now())
"""
from __future__ import annotations

import hashlib
import json
import logging
import pickle
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

from core.config import settings
from core.db.session import get_session
from .compound import CompoundDetector
from .ensemble import EnsembleScorer

logger = logging.getLogger(__name__)

# Risk score → bucket mapping
BUCKET_BREAKS = [(0, 25, "LOW"), (25, 50, "MEDIUM"), (50, 75, "HIGH"), (75, 100, "VERY_HIGH")]

# Supported hazard types and their feature tables
HAZARD_FEATURE_TABLES = {
    "flood":     "ml_features_flood",
    "wildfire":  "ml_features_wildfire",
    "heat_acute": "ml_features_heat",
}

HAZARD_FEATURE_COLS = {
    "flood": [
        "precipitation_7d_mm",
        "soil_saturation_index",
        "glofas_discharge_m3s",
        "sar_backscatter_db",
        "backscatter_anomaly_7d",
    ],
    "wildfire": [
        "firms_frp_mw",
        "gfs_wind_speed_ms",
        "gfs_relative_humidity_pct",
        "days_since_last_rain",
        "ndvi_index",
    ],
    "heat_acute": [
        "era5_temp_2m_c",
        "lst_kelvin",
        "days_above_35c_ytd",
        "urban_heat_island_factor",
    ],
}


@dataclass
class ScoringRunResult:
    hazard_type: str
    target_date: date
    n_cells_scored: int
    n_high_risk: int
    n_compound: int
    model_version: str
    elapsed_seconds: float
    errors: list[str] = field(default_factory=list)


def _score_to_bucket(score: float) -> str:
    for lo, hi, label in BUCKET_BREAKS:
        if lo <= score < hi:
            return label
    return "VERY_HIGH"


def _regulatory_fingerprint(
    h3_cell: str,
    hazard_type: str,
    scenario: str,
    observation_ids: list[str],
    model_version: str,
    scored_at: datetime,
    raw_score: float,
) -> str:
    """
    SHA-256 hash of all inputs that produced this score.

    A bank filing this score with the ECB in 2027 can verify it by sending
    us the fingerprint — we reproduce the hash from our immutable audit log.
    If it matches, the score is verified. Non-repudiable.
    """
    payload = json.dumps({
        "h3_cell":        h3_cell,
        "hazard_type":    hazard_type,
        "scenario":       scenario,
        "observation_ids": sorted(observation_ids),
        "model_version":  model_version,
        "scored_at":      scored_at.isoformat(),
        "raw_score":      round(raw_score, 6),
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _load_ensemble_scorer(model_version: str, hazard_type: str) -> Optional[EnsembleScorer]:
    """
    Load a serialised EnsembleScorer from the MLflow artifact store, or
    return None if no trained model exists yet.
    """
    try:
        import mlflow
        mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)

        client = mlflow.tracking.MlflowClient()
        runs = client.search_runs(
            experiment_ids=[
                e.experiment_id
                for e in client.search_experiments()
                if hazard_type in e.name
            ],
            filter_string=f"tags.model_version = '{model_version}'",
            max_results=1,
        )

        if not runs:
            # Fall back: find most recent successful run for this hazard
            experiments = client.search_experiments()
            exp_ids = [e.experiment_id for e in experiments if hazard_type in e.name]
            if not exp_ids:
                return None
            runs = client.search_runs(
                experiment_ids=exp_ids,
                filter_string="attributes.status = 'FINISHED'",
                order_by=["attributes.start_time DESC"],
                max_results=1,
            )

        if not runs:
            logger.warning(f"[Engine] No MLflow run found for {hazard_type} — "
                           "run train_{hazard_type}_model.py first")
            return None

        run = runs[0]
        artifact_uri = f"{run.info.artifact_uri}/scorer.pkl"
        local_path = mlflow.artifacts.download_artifacts(artifact_uri)
        with open(local_path, "rb") as f:
            scorer = pickle.load(f)
        logger.info(f"[Engine] Loaded EnsembleScorer from run {run.info.run_id}")
        return scorer

    except Exception as exc:
        logger.warning(f"[Engine] Could not load scorer from MLflow: {exc}")
        return None


def _fetch_features(hazard_type: str, target_date: date) -> pd.DataFrame:
    """Fetch ML features for target_date from the appropriate feature table."""
    table = HAZARD_FEATURE_TABLES[hazard_type]
    cols  = HAZARD_FEATURE_COLS[hazard_type]

    select_cols = ", ".join(
        f"CAST({c} AS FLOAT) AS {c}" for c in cols
    )

    with get_session() as session:
        rows = session.execute(text(f"""
            SELECT h3_cell, {select_cols}
            FROM   {table}
            WHERE  observed_at::date = :target_date
            ORDER  BY h3_cell
        """), {"target_date": str(target_date)}).mappings().all()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows)


def _fetch_velocity(
    h3_cells: list[str],
    hazard_type: str,
    reference_date: date,
    hours_back: int,
) -> dict[str, float]:
    """
    Fetch the most recent canonical score for each cell from `hours_back` hours ago.
    Returns {h3_cell: score} for cells that had a score in that window.
    """
    window_start = datetime.combine(reference_date, datetime.min.time()).replace(
        tzinfo=timezone.utc
    ) - timedelta(hours=hours_back + 12)
    window_end = window_start + timedelta(hours=24)

    with get_session() as session:
        rows = session.execute(text("""
            SELECT DISTINCT ON (h3_cell)
                   h3_cell,
                   CAST(risk_score AS FLOAT) AS risk_score
            FROM   canonical_scores
            WHERE  h3_cell     = ANY(:cells)
            AND    hazard_type = :hazard
            AND    scored_at  BETWEEN :start AND :end
            ORDER  BY h3_cell, scored_at DESC
        """), {
            "cells": h3_cells,
            "hazard": hazard_type,
            "start": window_start,
            "end":   window_end,
        }).fetchall()

    return {row[0]: float(row[1]) for row in rows}


def _retire_previous_scores(
    session,
    h3_cells: list[str],
    hazard_type: str,
    scenario: str,
    retired_at: datetime,
) -> int:
    """Set valid_to on all current scores for these cells (append-only pattern)."""
    result = session.execute(text("""
        UPDATE canonical_scores
        SET    valid_to = :retired_at
        WHERE  h3_cell     = ANY(:cells)
        AND    hazard_type = :hazard
        AND    scenario    = :scenario
        AND    valid_to    IS NULL
    """), {
        "retired_at": retired_at,
        "cells":      h3_cells,
        "hazard":     hazard_type,
        "scenario":   scenario,
    })
    return result.rowcount


def run(
    hazard_type: str,
    target_date: Optional[date] = None,
    scenario: str = "baseline",
    time_horizon: str = "current",
    model_version: str = "latest",
    dry_run: bool = False,
) -> ScoringRunResult:
    """
    Main entry point. Scores all H3 cells that have feature data for target_date.

    Parameters
    ----------
    hazard_type   : "flood" | "wildfire" | "heat_acute"
    target_date   : date to score (defaults to yesterday)
    scenario      : NGFS scenario label (default: "baseline")
    time_horizon  : "current" | "2030" | "2050" | "2100"
    model_version : MLflow model version tag or "latest"
    dry_run       : compute scores but do not write to DB
    """
    import time
    t0 = time.time()

    if hazard_type not in HAZARD_FEATURE_TABLES:
        raise ValueError(f"Unknown hazard_type '{hazard_type}'. "
                         f"Choose from: {list(HAZARD_FEATURE_TABLES)}")

    target_date = target_date or (date.today() - timedelta(days=1))
    scored_at   = datetime.now(timezone.utc)
    errors: list[str] = []

    logger.info(f"[Engine] ── Scoring run ──────────────────────────")
    logger.info(f"[Engine]   hazard      : {hazard_type}")
    logger.info(f"[Engine]   date        : {target_date}")
    logger.info(f"[Engine]   scenario    : {scenario}")
    logger.info(f"[Engine]   time_horizon: {time_horizon}")
    logger.info(f"[Engine]   dry_run     : {dry_run}")

    # ── 1. Load features ─────────────────────────────────────────
    features_df = _fetch_features(hazard_type, target_date)
    if features_df.empty:
        logger.warning(f"[Engine] No features for {hazard_type} on {target_date} — nothing to score")
        return ScoringRunResult(
            hazard_type=hazard_type, target_date=target_date,
            n_cells_scored=0, n_high_risk=0, n_compound=0,
            model_version=model_version, elapsed_seconds=time.time() - t0,
        )

    logger.info(f"[Engine] {len(features_df)} cells with features")

    # ── 2. Load ensemble scorer ──────────────────────────────────
    scorer = _load_ensemble_scorer(model_version, hazard_type)

    if scorer is None:
        # No trained model yet — produce a rule-based fallback score
        # (precipitation alone as a proxy), so the pipeline stays operational
        logger.warning("[Engine] No trained model — using rule-based fallback scorer")
        scored_df = _rule_based_fallback(features_df, hazard_type)
        actual_model_version = "fallback_rule_based_v1"
    else:
        scored_df = scorer.score_dataframe(features_df)
        actual_model_version = model_version

    # ── 3. Compute score velocity ─────────────────────────────────
    h3_cells = scored_df["h3_cell"].tolist()

    prior_6h  = _fetch_velocity(h3_cells, hazard_type, target_date, hours_back=6)
    prior_24h = _fetch_velocity(h3_cells, hazard_type, target_date, hours_back=24)
    prior_48h = _fetch_velocity(h3_cells, hazard_type, target_date, hours_back=48)

    scored_df["velocity_6h"]  = scored_df.apply(
        lambda r: round(r["score"] - prior_6h[r["h3_cell"]], 1)
        if r["h3_cell"] in prior_6h else None, axis=1
    )
    scored_df["velocity_24h"] = scored_df.apply(
        lambda r: round(r["score"] - prior_24h[r["h3_cell"]], 1)
        if r["h3_cell"] in prior_24h else None, axis=1
    )
    scored_df["velocity_48h"] = scored_df.apply(
        lambda r: round(r["score"] - prior_48h[r["h3_cell"]], 1)
        if r["h3_cell"] in prior_48h else None, axis=1
    )

    # ── 4. Compound event detection ───────────────────────────────
    with get_session() as session:
        detector = CompoundDetector(session)
        scored_df["compound_flag"] = detector.detect(target_date, scored_df, hazard_type)

    n_compound = int(scored_df["compound_flag"].sum())
    if n_compound:
        logger.info(f"[Engine] {n_compound} cells flagged as compound events")

    # ── 5. SHAP factors ───────────────────────────────────────────
    feature_cols = HAZARD_FEATURE_COLS[hazard_type]
    active_cols  = [c for c in feature_cols if c in scored_df.columns]
    shap_global  = None
    if scorer is not None:
        shap_global = scorer.shap_values(scored_df[active_cols].values)
        if shap_global:
            top = sorted(shap_global.items(), key=lambda x: -x[1])[:5]
            logger.info(f"[Engine] Top SHAP factors: {top}")

    # ── 6. Build score rows ───────────────────────────────────────
    records = []
    for _, row in scored_df.iterrows():
        score   = float(row["score"])
        h3_cell = str(row["h3_cell"])

        obs_ids: list[str] = []  # populated in future when observation FK is tracked

        fingerprint = _regulatory_fingerprint(
            h3_cell=h3_cell,
            hazard_type=hazard_type,
            scenario=scenario,
            observation_ids=obs_ids,
            model_version=actual_model_version,
            scored_at=scored_at,
            raw_score=score,
        )

        records.append({
            "score_id":               str(uuid.uuid4()),
            "h3_cell":                h3_cell,
            "h3_resolution":          settings.H3_RESOLUTION,
            "hazard_type":            hazard_type,
            "scenario":               scenario,
            "time_horizon":           time_horizon,
            "risk_score":             round(score, 2),
            "risk_bucket":            _score_to_bucket(score),
            "model_version":          actual_model_version,
            "data_vintage":           scored_at,
            "scored_at":              scored_at,
            "valid_from":             scored_at,
            "valid_to":               None,
            # ── IP layer ─────────────────────────────────────────
            "score_ci_lower":         row.get("ci_lower"),
            "score_ci_upper":         row.get("ci_upper"),
            "score_velocity_6h":      row.get("velocity_6h"),
            "score_velocity_24h":     row.get("velocity_24h"),
            "score_velocity_48h":     row.get("velocity_48h"),
            "ensemble_scores":        json.dumps(row.get("ensemble_scores", {})),
            "compound_flag":          bool(row.get("compound_flag", False)),
            "regulatory_fingerprint": fingerprint,
            "shap_factors":           json.dumps(shap_global or {}),
        })

    if dry_run:
        n_high = sum(1 for r in records if r["risk_score"] >= 50)
        logger.info(f"[Engine] DRY RUN — would write {len(records)} scores "
                    f"({n_high} HIGH/VERY_HIGH)")
        return ScoringRunResult(
            hazard_type=hazard_type, target_date=target_date,
            n_cells_scored=len(records), n_high_risk=n_high,
            n_compound=n_compound, model_version=actual_model_version,
            elapsed_seconds=round(time.time() - t0, 1),
        )

    # ── 7. Write to DB (append-only) ─────────────────────────────
    with get_session() as session:
        # Retire previous current scores
        retired = _retire_previous_scores(
            session, h3_cells, hazard_type, scenario, scored_at
        )
        logger.info(f"[Engine] Retired {retired} previous scores")

        # Insert new scores
        session.execute(text("""
            INSERT INTO canonical_scores (
                score_id, h3_cell, h3_resolution, hazard_type, scenario,
                time_horizon, risk_score, risk_bucket, model_version,
                data_vintage, shap_factors, scored_at, valid_from, valid_to,
                score_ci_lower, score_ci_upper,
                score_velocity_6h, score_velocity_24h, score_velocity_48h,
                ensemble_scores, compound_flag, regulatory_fingerprint
            ) VALUES (
                :score_id, :h3_cell, :h3_resolution, :hazard_type, :scenario,
                :time_horizon, :risk_score, :risk_bucket, :model_version,
                :data_vintage, :shap_factors::jsonb, :scored_at, :valid_from, :valid_to,
                :score_ci_lower, :score_ci_upper,
                :score_velocity_6h, :score_velocity_24h, :score_velocity_48h,
                :ensemble_scores::jsonb, :compound_flag, :regulatory_fingerprint
            )
        """), records)

    n_high = sum(1 for r in records if r["risk_score"] >= 50)
    elapsed = round(time.time() - t0, 1)
    logger.info(f"[Engine] ✓ {len(records)} scores written  "
                f"({n_high} HIGH+)  compound={n_compound}  {elapsed}s")

    return ScoringRunResult(
        hazard_type=hazard_type, target_date=target_date,
        n_cells_scored=len(records), n_high_risk=n_high,
        n_compound=n_compound, model_version=actual_model_version,
        elapsed_seconds=elapsed,
    )


def _rule_based_fallback(df: pd.DataFrame, hazard_type: str) -> pd.DataFrame:
    """
    Minimal rule-based scorer used when no trained model exists yet.
    Keeps the pipeline operational during initial data loading.
    Intentionally conservative — treat all cells as LOW-MEDIUM.
    """
    df = df.copy()

    if hazard_type == "flood":
        # Simple normalised sum of precipitation + runoff
        p = df.get("precipitation_7d_mm", pd.Series(0, index=df.index)).fillna(0)
        r = df.get("glofas_discharge_m3s", pd.Series(0, index=df.index)).fillna(0)
        s = df.get("soil_saturation_index", pd.Series(0, index=df.index)).fillna(0)
        p_norm = (p / p.max()).clip(0, 1) if p.max() > 0 else p
        r_norm = (r / r.max()).clip(0, 1) if r.max() > 0 else r
        raw = (0.5 * p_norm + 0.3 * r_norm + 0.2 * s) * 70  # cap at 70 (not VERY_HIGH)
    else:
        raw = pd.Series(20.0, index=df.index)  # default LOW

    df["score"]             = raw.clip(0, 100).round(1)
    df["ci_lower"]          = (df["score"] - 15).clip(0)
    df["ci_upper"]          = (df["score"] + 15).clip(0, 100)
    df["ensemble_scores"]   = [{"rule_based": s} for s in df["score"]]
    df["high_disagreement"] = False
    return df
