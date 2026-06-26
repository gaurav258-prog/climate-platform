"""
Unit tests for feature extraction computation logic.

All tests use synthetic DataFrames — no database required.
"""
import math
from datetime import datetime, timezone

import pandas as pd
import pytest

from ml.features.flood import FloodFeatureExtractor
from ml.features.heat import HeatFeatureExtractor
from ml.features.wildfire import (
    WildfireFeatureExtractor,
    _days_since_last_rain,
    relative_humidity,
    wind_speed,
)

# ── helpers ──────────────────────────────────────────────────────────────────

CELL_A = "88194ad337fffff"  # arbitrary valid-looking H3 index strings
CELL_B = "88194ad33bfffff"

TS1 = datetime(2024, 7, 25, 0, 0, tzinfo=timezone.utc)
TS2 = datetime(2024, 7, 26, 0, 0, tzinfo=timezone.utc)
TS3 = datetime(2024, 7, 27, 0, 0, tzinfo=timezone.utc)


def make_obs(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["h3_cell", "source_provider", "observed_at", "raw_value"])


# ── flood extractor ───────────────────────────────────────────────────────────

class TestFloodFeatures:

    def test_precipitation_converted_m_to_mm(self):
        obs = make_obs([
            {"h3_cell": CELL_A, "source_provider": "era5_total_precipitation", "observed_at": TS1, "raw_value": 0.005},
            {"h3_cell": CELL_A, "source_provider": "era5_total_precipitation", "observed_at": TS2, "raw_value": 0.003},
        ])
        features = FloodFeatureExtractor().compute_features(obs)
        row = features[features["h3_cell"] == CELL_A].iloc[0]
        assert abs(row["precipitation_7d_mm"] - 8.0) < 0.01  # (0.005 + 0.003) × 1000

    def test_backscatter_anomaly_is_latest_minus_mean(self):
        # Day 1: -15 dB, Day 2: -25 dB (drop = flood signature)
        obs = make_obs([
            {"h3_cell": CELL_A, "source_provider": "sentinel1_sar_grd", "observed_at": TS1, "raw_value": -15.0},
            {"h3_cell": CELL_A, "source_provider": "sentinel1_sar_grd", "observed_at": TS2, "raw_value": -25.0},
        ])
        features = FloodFeatureExtractor().compute_features(obs)
        row = features[features["h3_cell"] == CELL_A].iloc[0]
        # latest = -25, mean = (-15 + -25)/2 = -20 → anomaly = -25 - (-20) = -5
        assert abs(row["backscatter_anomaly_7d"] - (-5.0)) < 0.01

    def test_missing_provider_yields_null_column(self):
        # Only SAR data — no GloFAS
        obs = make_obs([
            {"h3_cell": CELL_A, "source_provider": "sentinel1_sar_grd", "observed_at": TS1, "raw_value": -12.0},
        ])
        features = FloodFeatureExtractor().compute_features(obs)
        row = features[features["h3_cell"] == CELL_A].iloc[0]
        assert "glofas_discharge_m3s" in features.columns
        assert row["glofas_discharge_m3s"] is None or math.isnan(float(row["glofas_discharge_m3s"] or float("nan")))

    def test_one_row_per_cell(self):
        obs = make_obs([
            {"h3_cell": CELL_A, "source_provider": "sentinel1_sar_grd", "observed_at": TS1, "raw_value": -12.0},
            {"h3_cell": CELL_A, "source_provider": "sentinel1_sar_grd", "observed_at": TS2, "raw_value": -14.0},
            {"h3_cell": CELL_B, "source_provider": "sentinel1_sar_grd", "observed_at": TS1, "raw_value": -8.0},
        ])
        features = FloodFeatureExtractor().compute_features(obs)
        assert len(features) == 2


# ── heat extractor ─────────────────────────────────────────────────────────────

class TestHeatFeatures:

    def test_temperature_converted_to_celsius(self):
        obs = make_obs([
            {"h3_cell": CELL_A, "source_provider": "era5_2m_temperature", "observed_at": TS1, "raw_value": 308.15},
        ])
        features = HeatFeatureExtractor().compute_features(obs)
        row = features[features["h3_cell"] == CELL_A].iloc[0]
        assert abs(row["era5_temp_2m_c"] - 35.0) < 0.01

    def test_days_above_35c_counts_correctly(self):
        obs = make_obs([
            # Day 1: 36°C = 309.15 K → above threshold
            {"h3_cell": CELL_A, "source_provider": "era5_2m_temperature", "observed_at": TS1, "raw_value": 309.15},
            # Day 2: 34°C = 307.15 K → below threshold
            {"h3_cell": CELL_A, "source_provider": "era5_2m_temperature", "observed_at": TS2, "raw_value": 307.15},
            # Day 3: 38°C = 311.15 K → above threshold
            {"h3_cell": CELL_A, "source_provider": "era5_2m_temperature", "observed_at": TS3, "raw_value": 311.15},
        ])
        features = HeatFeatureExtractor().compute_features(obs)
        row = features[features["h3_cell"] == CELL_A].iloc[0]
        assert row["days_above_35c_ytd"] == 2

    def test_no_hot_days_returns_zero(self):
        obs = make_obs([
            {"h3_cell": CELL_A, "source_provider": "era5_2m_temperature", "observed_at": TS1, "raw_value": 293.15},
        ])
        features = HeatFeatureExtractor().compute_features(obs)
        row = features[features["h3_cell"] == CELL_A].iloc[0]
        assert row["days_above_35c_ytd"] == 0


# ── wildfire pure functions ───────────────────────────────────────────────────

class TestWindSpeed:

    def test_pythagoras(self):
        assert abs(wind_speed(3.0, 4.0) - 5.0) < 1e-9

    def test_zero_wind(self):
        assert wind_speed(0.0, 0.0) == 0.0

    def test_none_input_returns_none(self):
        assert wind_speed(None, 3.0) is None
        assert wind_speed(3.0, None) is None


class TestRelativeHumidity:

    def test_dewpoint_equals_temperature_gives_100_pct(self):
        rh = relative_humidity(300.0, 300.0)
        assert abs(rh - 100.0) < 0.1

    def test_low_dewpoint_gives_low_humidity(self):
        # Hot dry day: T=40°C (313.15 K), Td=10°C (283.15 K)
        rh = relative_humidity(313.15, 283.15)
        assert rh < 30.0

    def test_result_clamped_to_0_100(self):
        # Dewpoint > temperature is physically impossible but should not crash
        rh = relative_humidity(273.15, 303.15)
        assert 0.0 <= rh <= 100.0

    def test_none_input_returns_none(self):
        assert relative_humidity(None, 280.0) is None


class TestDaysSinceLastRain:

    def test_consecutive_dry_days_counted(self):
        obs = make_obs([
            # Day 1: 5mm rain
            {"h3_cell": CELL_A, "source_provider": "era5_total_precipitation", "observed_at": TS1, "raw_value": 0.005},
            # Day 2: trace (dry)
            {"h3_cell": CELL_A, "source_provider": "era5_total_precipitation", "observed_at": TS2, "raw_value": 0.00001},
            # Day 3: trace (dry)
            {"h3_cell": CELL_A, "source_provider": "era5_total_precipitation", "observed_at": TS3, "raw_value": 0.00001},
        ])
        result = _days_since_last_rain(obs, threshold_mm=0.1)
        row = result[result["h3_cell"] == CELL_A].iloc[0]
        assert row["days_since_last_rain"] == 2

    def test_rain_on_latest_day_gives_zero(self):
        obs = make_obs([
            {"h3_cell": CELL_A, "source_provider": "era5_total_precipitation", "observed_at": TS1, "raw_value": 0.00001},
            {"h3_cell": CELL_A, "source_provider": "era5_total_precipitation", "observed_at": TS3, "raw_value": 0.010},
        ])
        result = _days_since_last_rain(obs, threshold_mm=0.1)
        row = result[result["h3_cell"] == CELL_A].iloc[0]
        assert row["days_since_last_rain"] == 0
