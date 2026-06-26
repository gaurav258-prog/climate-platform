"""
ECB Physical Climate Risk Format Builder.

Produces structured output aligned with:
  - ECB Guide on climate-related and environmental risks (Nov 2020)
  - ECB supervisory expectations: Pillar 2 physical risk assessment
  - EBA Pillar 3 ESG risk disclosure standards (Jan 2023)
  - NGFS scenario framework (baseline / orderly / disorderly / hot_house)

Output schema mirrors the ECB's expected disclosure tables:
  T1 — Physical risk exposure by geography (H3 cell → NUTS-2 region)
  T2 — Portfolio exposure by hazard type and risk bucket
  T3 — Scenario sensitivity (score delta vs baseline under 2030/2050/2100)
  T4 — High-risk asset concentration (VERY_HIGH cells, top-20)
  T5 — Methodology and model attestation

The package_data JSONB stored in regulatory_packages contains all five tables.
Each table row links back to the regulatory_fingerprint of the source score,
making every disclosure number independently verifiable.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# NGFS scenario labels we support
NGFS_SCENARIOS = ["baseline", "orderly", "disorderly", "hot_house"]

# Risk bucket ordering (for sort / aggregation)
BUCKET_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "VERY_HIGH": 3}

# ECB hazard type labels (their terminology)
ECB_HAZARD_LABELS = {
    "flood":      "River / Pluvial Flooding",
    "wildfire":   "Wildfire / Forest Fire",
    "heat_acute": "Extreme Heat",
    "drought":    "Drought",
    "sea_level":  "Coastal / Sea Level Rise",
}


def build(
    session: Session,
    customer_id: str,
    period_start: date,
    period_end: date,
    scenarios: Optional[list[str]] = None,
    time_horizons: Optional[list[str]] = None,
) -> dict:
    """
    Build the full ECB physical risk disclosure package for one customer.

    Returns a dict with keys t1..t5 + metadata. This becomes package_data in
    the regulatory_packages table.
    """
    scenarios     = scenarios     or ["baseline"]
    time_horizons = time_horizons or ["current", "2030", "2050"]

    logger.info(f"[ECB] Building package — customer={customer_id}  "
                f"{period_start}→{period_end}  "
                f"scenarios={scenarios}  horizons={time_horizons}")

    # ── Fetch customer locations + their scores ─────────────────
    location_scores = _fetch_location_scores(
        session, customer_id, period_start, period_end, scenarios, time_horizons
    )

    if not location_scores:
        logger.warning(f"[ECB] No scores found for customer {customer_id} in period")
        return _empty_package(customer_id, period_start, period_end)

    # ── T1: Physical risk exposure by geography ────────────────
    t1 = _table1_geographic(location_scores)

    # ── T2: Portfolio exposure by hazard × bucket ──────────────
    t2 = _table2_hazard_exposure(location_scores)

    # ── T3: Scenario sensitivity ───────────────────────────────
    t3 = _table3_scenario_sensitivity(location_scores, scenarios)

    # ── T4: High-risk asset concentration (top-20 VERY_HIGH) ──
    t4 = _table4_high_risk_concentration(location_scores)

    # ── T5: Methodology attestation ───────────────────────────
    t5 = _table5_methodology(location_scores)

    # ── Summary statistics ─────────────────────────────────────
    all_scores = [r["risk_score"] for r in location_scores]
    n_locations = len({r["location_id"] for r in location_scores})
    n_high_risk = sum(1 for r in location_scores if r["risk_bucket"] in ("HIGH", "VERY_HIGH"))

    return {
        "framework":          "ECB_PHYSICAL_RISK_2023",
        "customer_id":        customer_id,
        "period_start":       str(period_start),
        "period_end":         str(period_end),
        "scenarios_covered":  scenarios,
        "horizons_covered":   time_horizons,
        "n_locations":        n_locations,
        "n_score_records":    len(location_scores),
        "n_high_risk":        n_high_risk,
        "pct_high_risk":      round(n_high_risk / len(location_scores) * 100, 1) if location_scores else 0,
        "mean_score":         round(sum(all_scores) / len(all_scores), 1) if all_scores else 0,
        "t1_geographic":      t1,
        "t2_hazard_exposure": t2,
        "t3_scenario_sensitivity": t3,
        "t4_high_risk_assets": t4,
        "t5_methodology":     t5,
    }


def _fetch_location_scores(
    session: Session,
    customer_id: str,
    period_start: date,
    period_end: date,
    scenarios: list[str],
    time_horizons: list[str],
) -> list[dict]:
    """
    Join customer_locations → canonical_scores for the reporting period.
    Returns the most recent valid score per location per hazard per scenario.
    """
    rows = session.execute(text("""
        SELECT DISTINCT ON (cl.location_id, cs.hazard_type, cs.scenario, cs.time_horizon)
               cl.location_id,
               cl.location_name,
               cl.h3_cell_r8                         AS h3_cell,
               cl.asset_type,
               CAST(cl.asset_value AS FLOAT)          AS asset_value,
               cl.currency,
               cs.hazard_type,
               cs.scenario,
               cs.time_horizon,
               CAST(cs.risk_score AS FLOAT)           AS risk_score,
               cs.risk_bucket,
               cs.regulatory_fingerprint,
               cs.compound_flag,
               CAST(cs.score_ci_lower AS FLOAT)       AS ci_lower,
               CAST(cs.score_ci_upper AS FLOAT)       AS ci_upper,
               cs.scored_at
        FROM   customer_locations cl
        JOIN   canonical_scores   cs ON cs.h3_cell = cl.h3_cell_r8
        WHERE  cl.customer_id  = :customer_id
        AND    cl.is_active    = true
        AND    cs.scored_at   >= :period_start
        AND    cs.scored_at   <= :period_end
        AND    cs.scenario     = ANY(:scenarios)
        AND    cs.time_horizon = ANY(:horizons)
        AND    cs.valid_to     IS NULL
        ORDER BY cl.location_id, cs.hazard_type, cs.scenario, cs.time_horizon,
                 cs.scored_at DESC
    """), {
        "customer_id":  customer_id,
        "period_start": str(period_start),
        "period_end":   str(period_end),
        "scenarios":    scenarios,
        "horizons":     time_horizons,
    }).mappings().all()

    return [dict(r) for r in rows]


def _table1_geographic(rows: list[dict]) -> list[dict]:
    """T1: One row per location × hazard. Shows score + CI + compound flag."""
    seen = {}
    for r in rows:
        key = (r["location_id"], r["hazard_type"])
        if key not in seen or r["scenario"] == "baseline":
            seen[key] = {
                "location_id":    str(r["location_id"]),
                "location_name":  r["location_name"],
                "h3_cell":        r["h3_cell"],
                "asset_type":     r["asset_type"],
                "asset_value":    r["asset_value"],
                "currency":       r["currency"],
                "hazard_type":    r["hazard_type"],
                "hazard_label":   ECB_HAZARD_LABELS.get(r["hazard_type"], r["hazard_type"]),
                "risk_score":     r["risk_score"],
                "risk_bucket":    r["risk_bucket"],
                "ci_lower":       r["ci_lower"],
                "ci_upper":       r["ci_upper"],
                "compound_flag":  r["compound_flag"],
                "fingerprint":    r["regulatory_fingerprint"],
                "scored_at":      str(r["scored_at"]),
            }
    return sorted(seen.values(),
                  key=lambda x: (-BUCKET_ORDER.get(x["risk_bucket"], 0), x["location_name"] or ""))


def _table2_hazard_exposure(rows: list[dict]) -> list[dict]:
    """T2: Portfolio exposure by hazard × bucket. ECB's preferred summary table."""
    from collections import defaultdict

    # Aggregate: only baseline / current for the primary exposure view
    baseline = [r for r in rows if r["scenario"] == "baseline" and r["time_horizon"] == "current"]
    if not baseline:
        baseline = rows  # fall back to all

    buckets: dict[tuple, dict] = defaultdict(lambda: {
        "n_locations": 0, "total_asset_value": 0.0, "scores": []
    })

    for r in baseline:
        key = (r["hazard_type"], r["risk_bucket"])
        buckets[key]["n_locations"] += 1
        buckets[key]["total_asset_value"] += (r["asset_value"] or 0)
        buckets[key]["scores"].append(r["risk_score"])

    result = []
    total_locs = max(len({r["location_id"] for r in baseline}), 1)

    for (hazard, bucket), v in sorted(
        buckets.items(),
        key=lambda x: (x[0][0], -BUCKET_ORDER.get(x[0][1], 0))
    ):
        result.append({
            "hazard_type":       hazard,
            "hazard_label":      ECB_HAZARD_LABELS.get(hazard, hazard),
            "risk_bucket":       bucket,
            "n_locations":       v["n_locations"],
            "pct_portfolio":     round(v["n_locations"] / total_locs * 100, 1),
            "total_asset_value": round(v["total_asset_value"], 2),
            "mean_score":        round(sum(v["scores"]) / len(v["scores"]), 1),
        })

    return result


def _table3_scenario_sensitivity(rows: list[dict], scenarios: list[str]) -> list[dict]:
    """T3: Score delta vs baseline under each scenario × horizon."""
    # Build baseline lookup: location_id × hazard → score
    baseline_lookup: dict[tuple, float] = {}
    for r in rows:
        if r["scenario"] == "baseline" and r["time_horizon"] == "current":
            key = (str(r["location_id"]), r["hazard_type"])
            baseline_lookup[key] = r["risk_score"]

    result = []
    for r in rows:
        if r["scenario"] == "baseline" and r["time_horizon"] == "current":
            continue
        key = (str(r["location_id"]), r["hazard_type"])
        baseline = baseline_lookup.get(key)
        delta = round(r["risk_score"] - baseline, 1) if baseline is not None else None
        result.append({
            "location_id":   str(r["location_id"]),
            "location_name": r["location_name"],
            "hazard_type":   r["hazard_type"],
            "scenario":      r["scenario"],
            "time_horizon":  r["time_horizon"],
            "score":         r["risk_score"],
            "baseline_score": baseline,
            "delta_vs_baseline": delta,
            "fingerprint":   r["regulatory_fingerprint"],
        })

    return sorted(result, key=lambda x: (x["location_name"] or "", x["hazard_type"], x["time_horizon"]))


def _table4_high_risk_concentration(rows: list[dict]) -> list[dict]:
    """T4: Top-20 highest-risk locations by baseline current score."""
    baseline = [r for r in rows if r["scenario"] == "baseline" and r["time_horizon"] == "current"]
    if not baseline:
        baseline = rows
    sorted_rows = sorted(baseline, key=lambda x: -x["risk_score"])
    top20 = sorted_rows[:20]
    return [{
        "rank":          i + 1,
        "location_id":   str(r["location_id"]),
        "location_name": r["location_name"],
        "h3_cell":       r["h3_cell"],
        "asset_type":    r["asset_type"],
        "asset_value":   r["asset_value"],
        "currency":      r["currency"],
        "hazard_type":   r["hazard_type"],
        "risk_score":    r["risk_score"],
        "risk_bucket":   r["risk_bucket"],
        "compound_flag": r["compound_flag"],
        "fingerprint":   r["regulatory_fingerprint"],
    } for i, r in enumerate(top20)]


def _table5_methodology(rows: list[dict]) -> dict:
    """T5: Model attestation — model versions, score count, fingerprint summary."""
    fingerprints = [r["regulatory_fingerprint"] for r in rows if r["regulatory_fingerprint"]]
    scored_ats = [str(r["scored_at"]) for r in rows]

    return {
        "scoring_methodology":   "3-model ensemble (XGBoost + LightGBM + Logistic Regression)",
        "scenario_framework":    "NGFS Phase 4",
        "spatial_resolution":    "H3 resolution 8 (~0.7 km² cells)",
        "data_sources":          ["ERA5-Land (ECMWF)", "GloFAS discharge proxy",
                                  "Sentinel-1 SAR (where available)", "NASA FIRMS (where available)"],
        "n_scores_in_package":   len(rows),
        "n_fingerprints":        len(fingerprints),
        "earliest_score":        min(scored_ats) if scored_ats else None,
        "latest_score":          max(scored_ats) if scored_ats else None,
        "fingerprint_algorithm": "SHA-256",
        "note": ("Each score in this package is independently verifiable via its "
                 "regulatory_fingerprint — a SHA-256 hash of all model inputs. "
                 "Present the fingerprint to the platform operator to reproduce "
                 "the exact score on demand."),
    }


def _empty_package(customer_id: str, period_start: date, period_end: date) -> dict:
    return {
        "framework":      "ECB_PHYSICAL_RISK_2023",
        "customer_id":    customer_id,
        "period_start":   str(period_start),
        "period_end":     str(period_end),
        "n_locations":    0,
        "n_score_records": 0,
        "warning":        "No canonical scores found for this customer in the reporting period.",
        "t1_geographic":  [],
        "t2_hazard_exposure": [],
        "t3_scenario_sensitivity": [],
        "t4_high_risk_assets": [],
        "t5_methodology": {},
    }
