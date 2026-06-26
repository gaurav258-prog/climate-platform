"""
Heat stress risk classifier — 3-model ensemble.

Trains on ml_features_heat rows where heat_event_occurred IS NOT NULL.

Features available from ERA5 + Sentinel-3 LST backfill:
  lst_anomaly_vs_baseline   — land surface temp deviation from 30yr mean (K)
  era5_temp_2m_c            — 2m air temperature (°C)
  era5_temp_30yr_mean       — climatological baseline (°C)
  era5_temp_trend_per_decade — warming trend signal (°C/decade)
  urban_heat_island_factor  — UHI amplification factor (1.0 = rural baseline)
  days_above_35c_ytd        — cumulative heat days this year (stress proxy)

Future features (NULL until loaded):
  population_density        — exposure weighting for health impact scoring
  lst_kelvin                — Sentinel-3 SLSTR raw LST for anomaly computation

scale_pos_weight 15.0 — heat events are uncommon but less rare than wildfire.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import text

from core.db.session import get_session

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "lst_anomaly_vs_baseline",
    "era5_temp_2m_c",
    "era5_temp_30yr_mean",
    "era5_temp_trend_per_decade",
    "urban_heat_island_factor",
    "days_above_35c_ytd",
]

FUTURE_COLS = [
    "population_density",  # exposure weighting once census layer is loaded
    "lst_kelvin",          # raw LST from Sentinel-3 SLSTR
]

LABEL_COL = "heat_event_occurred"


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
    Load labeled heat feature rows from ml_features_heat.

    Temporal split on train_end / test_start; random 80/20 if not given.
    """
    sql = text("""
        SELECT
            h3_cell,
            observed_at::date                           AS obs_date,
            CAST(lst_anomaly_vs_baseline    AS FLOAT)   AS lst_anomaly_vs_baseline,
            CAST(era5_temp_2m_c             AS FLOAT)   AS era5_temp_2m_c,
            CAST(era5_temp_30yr_mean        AS FLOAT)   AS era5_temp_30yr_mean,
            CAST(era5_temp_trend_per_decade AS FLOAT)   AS era5_temp_trend_per_decade,
            CAST(urban_heat_island_factor   AS FLOAT)   AS urban_heat_island_factor,
            CAST(days_above_35c_ytd         AS FLOAT)   AS days_above_35c_ytd,
            heat_event_occurred::int                    AS heat_event_occurred
        FROM ml_features_heat
        WHERE heat_event_occurred IS NOT NULL
        ORDER BY observed_at
    """)

    with get_session() as session:
        rows = session.execute(sql).mappings().all()

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("No labeled rows in ml_features_heat. "
                         "Run load_ground_truth_labels.py first.")

    logger.info(f"Loaded {len(df)} labeled rows  "
                f"(positive={df['heat_event_occurred'].sum()}, "
                f"negative={(df['heat_event_occurred'] == 0).sum()})")

    if train_end and test_start:
        train_df = df[df["obs_date"] <= train_end].copy()
        test_df  = df[df["obs_date"] >= test_start].copy()
    else:
        from sklearn.model_selection import train_test_split
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42,
                                             stratify=df[LABEL_COL])

    logger.info(f"Train: {len(train_df)} rows  |  Test: {len(test_df)} rows")
    return train_df, test_df


def train(
    train_end: Optional[date] = None,
    test_start: Optional[date] = None,
    mlflow_uri: Optional[str] = None,
    register: bool = True,
) -> TrainResult:
    """
    Full training run. Trains 3-model ensemble, logs to MLflow, persists scorer.pkl.
    """
    import os
    import pickle
    import tempfile

    import mlflow
    import mlflow.xgboost
    from sklearn.metrics import average_precision_score, classification_report, roc_auc_score

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

    model_version = f"heat-v{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"

    mlflow.set_experiment("heat-risk-ensemble")
    with mlflow.start_run(run_name=model_version) as run:
        scorer = EnsembleScorer(scale_pos_weight=15.0)
        scorer.fit(X_train, y_train, feature_cols=active_features)
        mlflow.set_tag("model_version", model_version)
        mlflow.set_tag("hazard_type", "heat_acute")

        ensemble_df = scorer.score_dataframe(
            test_df[active_features].assign(h3_cell="eval")
        )
        y_prob = (ensemble_df["score"] / 100).values
        y_pred = (y_prob >= 0.5).astype(int)

        auc = (roc_auc_score(y_test, y_prob)
               if len(np.unique(y_test)) > 1 else float("nan"))
        ap  = (average_precision_score(y_test, y_prob)
               if len(np.unique(y_test)) > 1 else float("nan"))
        report = classification_report(y_test, y_pred,
                                       target_names=["no_heat_event", "heat_event"],
                                       zero_division=0)

        mlflow.log_params({
            "n_estimators":     300,
            "max_depth":        4,
            "learning_rate":    0.05,
            "scale_pos_weight": 15.0,
            "ensemble_models":  ",".join(scorer._pipelines.keys()),
            "features":         ",".join(active_features),
            "n_train":          len(X_train),
            "n_test":           len(X_test),
        })
        mlflow.log_metrics({
            "roc_auc":           round(auc, 4),
            "avg_precision":     round(ap, 4),
            "n_positive_train":  int(y_train.sum()),
            "n_positive_test":   int(y_test.sum()),
        })

        fi: dict[str, float] = {}
        if "xgb" in scorer._pipelines:
            xgb_clf = scorer._pipelines["xgb"].named_steps["clf"]
            fi = dict(zip(active_features, xgb_clf.feature_importances_))
            for fname, fscore in fi.items():
                mlflow.log_metric(f"fi_{fname}", round(float(fscore), 4))
            mlflow.xgboost.log_model(xgb_clf, artifact_path="xgboost_model")

        scorer_dir = tempfile.mkdtemp()
        scorer_path = os.path.join(scorer_dir, "scorer.pkl")
        with open(scorer_path, "wb") as f:
            pickle.dump(scorer, f)
        mlflow.log_artifact(scorer_path)

        logger.info(f"\n  ROC-AUC:            {auc:.4f}")
        logger.info(f"  Avg Precision:      {ap:.4f}")
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
    with get_session() as session:
        session.execute(text("""
            INSERT INTO model_registry
                (model_id, model_version, hazard_type, algorithm,
                 training_data_vintage, training_cell_count,
                 validation_auc, is_active, created_at)
            VALUES
                (:model_id, :version, 'heat_acute', 'xgboost',
                 :vintage, :n_train,
                 :auc, false, now())
            ON CONFLICT (model_version) DO NOTHING
        """), {
            "model_id": str(uuid.uuid4()),
            "version":  result.model_version,
            "vintage":  data_vintage,
            "n_train":  result.n_train,
            "auc":      round(result.roc_auc, 3) if not np.isnan(result.roc_auc) else None,
        })
    logger.info(f"Registered model {result.model_version} in model_registry")
