"""
Drought risk classifier — completes the drought hazard model.

Mirrors the flood/heat/wildfire trainers: it learns P(drought) from
ml_features_drought rows where drought_occurred IS NOT NULL, using the shared
3-model EnsembleScorer (XGBoost + LightGBM + Logistic). The engine then turns
those probabilities into 0–100 canonical drought scores.

Predictive features (all in ml_features_drought):
  spi_3month                — Standardized Precipitation Index (low = dry)
  spei_3month               — SPI adjusted for evapotranspiration
  soil_moisture_percentile  — soil water vs local climatology
  precipitation_deficit_mm  — shortfall vs normal
  ndvi_anomaly_vs_baseline  — vegetation stress (negative = stressed)
  era5_temp_anomaly_c       — temperature anomaly
  days_since_significant_rain

The DB/MLflow paths mirror flood_model.py. The pure `train_on_dataframe()` core
holds the actual learning + evaluation so it is testable without a database.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split

from ml.scoring.ensemble import EnsembleScorer

logger = logging.getLogger(__name__)

FEATURE_COLS = [
    "spi_3month",
    "spei_3month",
    "soil_moisture_percentile",
    "precipitation_deficit_mm",
    "ndvi_anomaly_vs_baseline",
    "era5_temp_anomaly_c",
    "days_since_significant_rain",
]

LABEL_COL = "drought_occurred"

# Drought cells are the minority class (dry spells are rarer than normal months).
SCALE_POS_WEIGHT = 8.0


@dataclass
class TrainResult:
    model_version: str
    roc_auc: float
    avg_precision: float
    n_train: int
    n_test: int
    n_positive_train: int
    feature_cols: list[str] = field(default_factory=list)


# ── Pure core: learn + evaluate on a DataFrame (no DB, no MLflow) ────────────

def train_on_dataframe(
    df: pd.DataFrame,
    *,
    test_size: float = 0.2,
    random_state: int = 42,
    model_version: Optional[str] = None,
) -> tuple[EnsembleScorer, TrainResult]:
    """
    Fit the ensemble on a labeled drought DataFrame and evaluate on a holdout.
    `df` must contain FEATURE_COLS + LABEL_COL. Returns (fitted scorer, metrics).
    """
    active = [c for c in FEATURE_COLS if c in df.columns]
    if not active:
        raise ValueError("none of FEATURE_COLS present in dataframe")
    if df[LABEL_COL].nunique() < 2:
        raise ValueError("need both drought and non-drought rows to train")

    train_df, test_df = train_test_split(
        df, test_size=test_size, random_state=random_state, stratify=df[LABEL_COL],
    )

    X_train = train_df[active].values
    y_train = train_df[LABEL_COL].values.astype(int)

    scorer = EnsembleScorer(scale_pos_weight=SCALE_POS_WEIGHT)
    scorer.fit(X_train, y_train, feature_cols=active)

    scored = scorer.score_dataframe(test_df[active].copy())
    y_prob = (scored["score"] / 100.0).values
    y_test = test_df[LABEL_COL].values.astype(int)

    auc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else float("nan")
    ap = average_precision_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else float("nan")

    version = model_version or f"drought-v{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
    result = TrainResult(
        model_version=version,
        roc_auc=float(auc),
        avg_precision=float(ap),
        n_train=len(train_df),
        n_test=len(test_df),
        n_positive_train=int(y_train.sum()),
        feature_cols=active,
    )
    logger.info(f"[drought] trained {version}: ROC-AUC={auc:.4f} AP={ap:.4f} "
                f"({result.n_train} train / {result.n_test} test)")
    return scorer, result


# ── DB / MLflow production path (mirrors flood_model.py) ─────────────────────

def load_labeled_features() -> pd.DataFrame:
    """Load labeled rows from ml_features_drought."""
    from sqlalchemy import text

    from core.db.session import get_session

    cols = ",\n            ".join(f"CAST({c} AS FLOAT) AS {c}" for c in FEATURE_COLS)
    sql = text(f"""
        SELECT h3_cell, observed_at::date AS obs_date,
            {cols},
            {LABEL_COL}::int AS {LABEL_COL}
        FROM ml_features_drought
        WHERE {LABEL_COL} IS NOT NULL
        ORDER BY observed_at
    """)
    with get_session() as session:
        rows = session.execute(sql).mappings().all()
    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("No labeled rows in ml_features_drought. "
                         "Load drought ground-truth labels first.")
    return df


def train(register: bool = True, mlflow_uri: Optional[str] = None) -> TrainResult:
    """Full training run: load → fit → log to MLflow → register. Mirrors flood."""
    import os
    import pickle
    import tempfile

    import mlflow

    df = load_labeled_features()
    scorer, result = train_on_dataframe(df)

    if mlflow_uri:
        mlflow.set_tracking_uri(mlflow_uri)
    mlflow.set_experiment("drought-risk-ensemble")
    with mlflow.start_run(run_name=result.model_version) as run:
        mlflow.set_tag("model_version", result.model_version)
        mlflow.log_params({"features": ",".join(result.feature_cols),
                           "scale_pos_weight": SCALE_POS_WEIGHT,
                           "n_train": result.n_train, "n_test": result.n_test})
        mlflow.log_metrics({"roc_auc": round(result.roc_auc, 4),
                            "avg_precision": round(result.avg_precision, 4)})
        scorer_dir = tempfile.mkdtemp()
        scorer_path = os.path.join(scorer_dir, "scorer.pkl")
        with open(scorer_path, "wb") as f:
            pickle.dump(scorer, f)
        mlflow.log_artifact(scorer_path)
        run_id = run.info.run_id

    if register:
        _register_model(result, run_id, df["obs_date"].min())
    return result


def _register_model(result: TrainResult, mlflow_run_id: str, data_vintage: date) -> None:
    from sqlalchemy import text

    from core.db.session import get_session

    with get_session() as session:
        session.execute(text("""
            INSERT INTO model_registry
                (model_id, model_version, hazard_type, algorithm,
                 training_data_vintage, training_cell_count, validation_auc,
                 is_active, created_at)
            VALUES
                (:model_id, :version, 'drought', 'ensemble_xgb_lgbm_logistic',
                 :vintage, :n_train, :auc, false, now())
            ON CONFLICT (model_version) DO NOTHING
        """), {
            "model_id": str(uuid.uuid4()),
            "version": result.model_version,
            "vintage": data_vintage,
            "n_train": result.n_train,
            "auc": round(result.roc_auc, 3) if not np.isnan(result.roc_auc) else None,
        })
    logger.info(f"Registered drought model {result.model_version}")
