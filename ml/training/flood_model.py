"""
XGBoost flood risk classifier.

Trains on ml_features_flood rows where flood_occurred IS NOT NULL.
Features available from ERA5 backfill:
  precipitation_7d_mm   — 7-day cumulative precipitation (mm)
  soil_saturation_index — ERA5 volumetric soil water layer 1 (m³/m³)
  glofas_discharge_m3s  — ERA5-Land total runoff (m, stored as proxy discharge)

Future features (NULL until separate data loads):
  sar_backscatter_db, backscatter_anomaly_7d (Sentinel-1)
  dem_elevation_m, dem_slope_degrees, distance_to_water_km (EU DEM)
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score, classification_report, roc_auc_score
)
from sklearn.pipeline import Pipeline
from sqlalchemy import text

from core.db.session import get_session

logger = logging.getLogger(__name__)

# Features that exist in the DB now (post-ERA5 backfill)
# Extend this list as more data sources come online
FEATURE_COLS = [
    "precipitation_7d_mm",
    "soil_saturation_index",
    "glofas_discharge_m3s",
]

# Feature columns that may arrive later
FUTURE_COLS = [
    "sar_backscatter_db",
    "backscatter_anomaly_7d",
    "dem_elevation_m",
    "dem_slope_degrees",
    "distance_to_water_km",
]

LABEL_COL = "flood_occurred"


@dataclass
class TrainResult:
    model_version: str
    roc_auc: float
    avg_precision: float
    n_train: int
    n_test: int
    feature_importance: dict[str, float] = field(default_factory=dict)
    classification_report: str = ""


def load_labeled_features(
    train_end: Optional[date] = None,
    test_start: Optional[date] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load feature rows that have ground truth labels.

    Temporal split: rows on or before train_end → train, rows from test_start → test.
    If neither is given, uses a random 80/20 split (for ad-hoc runs).

    Returns (train_df, test_df) — columns include FEATURE_COLS + LABEL_COL.
    """
    sql = text("""
        SELECT
            h3_cell,
            observed_at::date                       AS obs_date,
            CAST(precipitation_7d_mm    AS FLOAT)   AS precipitation_7d_mm,
            CAST(soil_saturation_index  AS FLOAT)   AS soil_saturation_index,
            CAST(glofas_discharge_m3s   AS FLOAT)   AS glofas_discharge_m3s,
            CAST(sar_backscatter_db     AS FLOAT)   AS sar_backscatter_db,
            CAST(backscatter_anomaly_7d AS FLOAT)   AS backscatter_anomaly_7d,
            flood_occurred::int                     AS flood_occurred
        FROM ml_features_flood
        WHERE flood_occurred IS NOT NULL
        ORDER BY observed_at
    """)

    with get_session() as session:
        rows = session.execute(sql).mappings().all()

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("No labeled rows in ml_features_flood. "
                         "Run load_ground_truth_labels.py first.")

    logger.info(f"Loaded {len(df)} labeled rows  "
                f"(positive={df['flood_occurred'].sum()}, "
                f"negative={(df['flood_occurred']==0).sum()})")

    if train_end and test_start:
        train_df = df[df["obs_date"] <= train_end].copy()
        test_df  = df[df["obs_date"] >= test_start].copy()
    else:
        from sklearn.model_selection import train_test_split
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42,
                                             stratify=df[LABEL_COL])

    logger.info(f"Train: {len(train_df)} rows  |  Test: {len(test_df)} rows")
    return train_df, test_df


def _build_pipeline(n_estimators: int = 300, max_depth: int = 4,
                    learning_rate: float = 0.05) -> Pipeline:
    """Build sklearn Pipeline: median imputer → XGBoost classifier."""
    pos_weight = 10.0  # flood cells are minority class

    clf = xgb.XGBClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        learning_rate=learning_rate,
        scale_pos_weight=pos_weight,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
        tree_method="hist",
    )

    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("clf", clf),
    ])


def train(
    train_end: Optional[date] = None,
    test_start: Optional[date] = None,
    mlflow_uri: Optional[str] = None,
    register: bool = True,
) -> TrainResult:
    """
    Full training run. Trains 3-model ensemble, logs to MLflow, persists scorer.pkl.
    """
    import pickle
    import tempfile
    import mlflow
    import mlflow.xgboost

    from ml.scoring.ensemble import EnsembleScorer

    if mlflow_uri:
        mlflow.set_tracking_uri(mlflow_uri)

    train_df, test_df = load_labeled_features(train_end, test_start)

    active_features = [c for c in FEATURE_COLS if c in train_df.columns]
    logger.info(f"Training on features: {active_features}")

    X_train = train_df[active_features].values
    y_train = train_df[LABEL_COL].values.astype(int)
    X_test  = test_df[active_features].values
    y_test  = test_df[LABEL_COL].values.astype(int)

    model_version = f"flood-v{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"

    mlflow.set_experiment("flood-risk-xgboost")
    with mlflow.start_run(run_name=model_version) as run:
        # Train ensemble (XGBoost + LightGBM + Logistic)
        scorer = EnsembleScorer(scale_pos_weight=10.0)
        scorer.fit(X_train, y_train, feature_cols=active_features)
        mlflow.set_tag("model_version", model_version)

        # Evaluate using ensemble mean probability
        ensemble_df = scorer.score_dataframe(test_df[active_features].assign(h3_cell="eval"))
        y_prob = (ensemble_df["score"] / 100).values
        y_pred = (y_prob >= 0.5).astype(int)

        auc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else float("nan")
        ap  = average_precision_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else float("nan")
        report = classification_report(y_test, y_pred,
                                       target_names=["no_flood", "flood"],
                                       zero_division=0)

        mlflow.log_params({
            "n_estimators": 300,
            "max_depth": 4,
            "learning_rate": 0.05,
            "scale_pos_weight": 10.0,
            "ensemble_models": ",".join(scorer._pipelines.keys()),
            "features": ",".join(active_features),
            "n_train": len(X_train),
            "n_test": len(X_test),
        })
        mlflow.log_metrics({
            "roc_auc": round(auc, 4),
            "avg_precision": round(ap, 4),
            "n_positive_train": int(y_train.sum()),
            "n_positive_test": int(y_test.sum()),
        })

        # Log XGBoost native model for MLflow UI (optional)
        if "xgb" in scorer._pipelines:
            xgb_clf = scorer._pipelines["xgb"].named_steps["clf"]
            fi = dict(zip(active_features, xgb_clf.feature_importances_))
            for fname, fscore in fi.items():
                mlflow.log_metric(f"fi_{fname}", round(float(fscore), 4))
            mlflow.xgboost.log_model(xgb_clf, artifact_path="xgboost_model")
        else:
            fi = {}

        # Persist the full EnsembleScorer as scorer.pkl — what the engine loads
        # Use tempdir so the file is named exactly "scorer.pkl" at the artifact root
        import os
        scorer_dir = tempfile.mkdtemp()
        scorer_path = os.path.join(scorer_dir, "scorer.pkl")
        with open(scorer_path, "wb") as f:
            pickle.dump(scorer, f)
        mlflow.log_artifact(scorer_path)  # artifact_uri/scorer.pkl at root

        logger.info(f"\n  ROC-AUC:         {auc:.4f}")
        logger.info(f"  Avg Precision:   {ap:.4f}")
        logger.info(f"  Models in ensemble: {list(scorer._pipelines.keys())}")
        logger.info(f"\n{report}")

        run_id = run.info.run_id

    result = TrainResult(
        model_version=model_version,
        roc_auc=auc,
        avg_precision=ap,
        n_train=len(X_train),
        n_test=len(X_test),
        feature_importance=fi,
        classification_report=report,
    )

    if register:
        _register_model(result, run_id, active_features, train_df["obs_date"].min())

    return result


def _register_model(result: TrainResult, mlflow_run_id: str,
                    features: list[str], data_vintage: date) -> None:
    """Write model metadata to canonical model_registry table."""
    from sqlalchemy import text
    from core.db.session import get_session

    with get_session() as session:
        session.execute(text("""
            INSERT INTO model_registry
                (model_id, model_version, hazard_type, algorithm,
                 training_data_vintage, training_cell_count,
                 validation_auc, is_active, created_at)
            VALUES
                (:model_id, :version, 'flood', 'xgboost',
                 :vintage, :n_train,
                 :auc, false, now())
            ON CONFLICT (model_version) DO NOTHING
        """), {
            "model_id": str(uuid.uuid4()),
            "version": result.model_version,
            "vintage": data_vintage,
            "n_train": result.n_train,
            "auc": round(result.roc_auc, 3) if not np.isnan(result.roc_auc) else None,
        })

    logger.info(f"Registered model {result.model_version} in model_registry")


def score_cells(
    model_pipeline: Pipeline,
    target_date: date,
    features: list[str] | None = None,
) -> pd.DataFrame:
    """
    Run inference for all cells with feature data on `target_date`.

    Returns DataFrame: h3_cell, risk_score (0–100), risk_bucket
    """
    if features is None:
        features = FEATURE_COLS

    sql = text("""
        SELECT
            h3_cell,
            CAST(precipitation_7d_mm    AS FLOAT) AS precipitation_7d_mm,
            CAST(soil_saturation_index  AS FLOAT) AS soil_saturation_index,
            CAST(glofas_discharge_m3s   AS FLOAT) AS glofas_discharge_m3s
        FROM ml_features_flood
        WHERE observed_at::date = :target_date
        ORDER BY h3_cell
    """)

    with get_session() as session:
        rows = session.execute(sql, {"target_date": str(target_date)}).mappings().all()

    if not rows:
        logger.warning(f"No feature rows found for {target_date}")
        return pd.DataFrame(columns=["h3_cell", "risk_score", "risk_bucket"])

    df = pd.DataFrame(rows)
    active = [c for c in features if c in df.columns]

    probs = model_pipeline.predict_proba(df[active].values)[:, 1]
    df["risk_score"] = (probs * 100).round(1)
    df["risk_bucket"] = pd.cut(
        df["risk_score"],
        bins=[-0.1, 25, 50, 75, 100],
        labels=["LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
    )
    return df[["h3_cell", "risk_score", "risk_bucket"]]
