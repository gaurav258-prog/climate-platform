"""
Tests for the drought model.

The headline test trains the real 3-model ensemble on a physically-grounded
synthetic drought dataset and asserts it learns the signal (holdout ROC-AUC).
This proves the model works end-to-end; it does NOT replace training on real
ml_features_drought data once the drought ETL runs.

Also checks the engine wiring (drought registered, sensible rule-based fallback).
"""

import numpy as np
import pandas as pd
import pytest

from ml.scoring.engine import (
    HAZARD_FEATURE_COLS,
    HAZARD_FEATURE_TABLES,
    _rule_based_fallback,
)
from ml.training.drought_model import FEATURE_COLS, LABEL_COL, train_on_dataframe


def _synthetic_drought(n=1500, seed=42):
    """
    Generate labeled drought rows with a real latent signal: drought becomes more
    likely as SPI/SPEI fall, soil dries, deficit and dry-spell grow, temp rises.
    Returns a DataFrame with FEATURE_COLS + LABEL_COL.
    """
    rng = np.random.default_rng(seed)
    # Two partly-independent meteorological drivers so the signal isn't a single
    # collinear axis: a precipitation regime and a temperature regime.
    precip_z = rng.normal(0, 1, n)      # negative = dry
    temp_z = rng.normal(0, 1, n)        # positive = hot

    spi = precip_z + rng.normal(0, 0.3, n)
    spei = 0.6 * precip_z + 0.4 * temp_z + rng.normal(0, 0.3, n)
    soil_pct = np.clip(50 + precip_z * 18 + rng.normal(0, 8, n), 0, 100)
    precip_deficit = np.clip(-precip_z * 45 + rng.normal(0, 15, n), 0, None)
    ndvi_anom = 0.12 * precip_z - 0.05 * temp_z + rng.normal(0, 0.05, n)
    temp_anom = 1.5 * temp_z + rng.normal(0, 0.4, n)
    days_dry = np.clip(-precip_z * 14 + 20 + rng.normal(0, 5, n), 0, None)

    # Drought = sustained dry AND hot. Clear latent signal, modest label noise,
    # intercept tuned for a realistic minority positive rate.
    latent = -1.4 * precip_z + 0.8 * temp_z
    z = (latent - latent.mean()) / latent.std()
    prob = 1 / (1 + np.exp(-(2.6 * z - 1.1)))
    label = (rng.uniform(0, 1, n) < prob).astype(int)  # minority positive

    return pd.DataFrame({
        "spi_3month": spi,
        "spei_3month": spei,
        "soil_moisture_percentile": soil_pct,
        "precipitation_deficit_mm": precip_deficit,
        "ndvi_anomaly_vs_baseline": ndvi_anom,
        "era5_temp_anomaly_c": temp_anom,
        "days_since_significant_rain": days_dry,
        LABEL_COL: label,
    })


# ── The model learns ─────────────────────────────────────────────────────────

def test_ensemble_learns_drought_signal():
    df = _synthetic_drought()
    scorer, result = train_on_dataframe(df, model_version="drought-test")
    assert result.roc_auc > 0.80          # learns a strong signal from the features
    assert result.n_positive_train > 0
    assert set(result.feature_cols) == set(FEATURE_COLS)


def test_score_rises_with_drought_stress():
    df = _synthetic_drought()
    scorer, _ = train_on_dataframe(df, model_version="drought-test")
    # A clearly dry cell should score higher than a clearly wet one.
    dry = pd.DataFrame([{
        "spi_3month": -2.5, "spei_3month": -2.3, "soil_moisture_percentile": 5,
        "precipitation_deficit_mm": 120, "ndvi_anomaly_vs_baseline": -0.25,
        "era5_temp_anomaly_c": 3.0, "days_since_significant_rain": 60,
    }])
    wet = pd.DataFrame([{
        "spi_3month": 2.0, "spei_3month": 1.8, "soil_moisture_percentile": 95,
        "precipitation_deficit_mm": 0, "ndvi_anomaly_vs_baseline": 0.15,
        "era5_temp_anomaly_c": -1.0, "days_since_significant_rain": 2,
    }])
    dry_score = scorer.score_dataframe(dry)["score"].iloc[0]
    wet_score = scorer.score_dataframe(wet)["score"].iloc[0]
    assert dry_score > wet_score
    assert dry_score > 50


def test_training_needs_both_classes():
    df = _synthetic_drought()
    df[LABEL_COL] = 0                      # all negative
    with pytest.raises(ValueError, match="both drought and non-drought"):
        train_on_dataframe(df)


# ── Engine wiring ────────────────────────────────────────────────────────────

def test_drought_registered_in_engine():
    assert HAZARD_FEATURE_TABLES["drought"] == "ml_features_drought"
    assert "spi_3month" in HAZARD_FEATURE_COLS["drought"]


def test_rule_based_fallback_ranks_drought_cells():
    df = pd.DataFrame([
        {"h3_cell": "dry", "spi_3month": -2.4, "spei_3month": -2.2,
         "soil_moisture_percentile": 8, "days_since_significant_rain": 55},
        {"h3_cell": "wet", "spi_3month": 1.8, "spei_3month": 1.5,
         "soil_moisture_percentile": 90, "days_since_significant_rain": 3},
    ])
    scored = _rule_based_fallback(df, "drought")
    dry = scored[scored.h3_cell == "dry"]["score"].iloc[0]
    wet = scored[scored.h3_cell == "wet"]["score"].iloc[0]
    assert dry > wet
    assert dry <= 70                       # rule-based is capped below VERY_HIGH
