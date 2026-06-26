"""
Flood feature extractor.

Sources joined per H3 cell:
  sentinel1_sar_grd      → SAR backscatter (dB)
  glofas_era5_reanalysis → river discharge (m³/s)
  era5_total_precipitation → daily precip (m)
  era5_soil_moisture_l1  → volumetric soil water (m³/m³)

Derived features computed here:
  backscatter_anomaly_7d  — latest SAR minus 7-day mean (detects sudden inundation)
  precipitation_7d_mm     — 7-day cumulative precipitation in mm

Static features (dem_elevation_m, dem_slope_degrees, distance_to_water_km) are NULL
until the EU DEM one-time load is complete (separate data task).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

import pandas as pd

from core.db.models import MLFeatureFlood
from core.db.session import get_session
from .base import BaseFeatureExtractor

logger = logging.getLogger(__name__)

SOURCES = [
    "sentinel1_sar_grd",
    "era5_total_runoff",
    "era5_total_precipitation",
    "era5_soil_moisture_l1",
]


class FloodFeatureExtractor(BaseFeatureExtractor):

    def extract(self, target_date: date) -> int:
        obs = self._fetch_observations(SOURCES, target_date, lookback_days=7)

        if obs.empty:
            logger.info(f"[FloodFeatures] no observations for {target_date} — skipping")
            return 0

        features = self.compute_features(obs)
        if features.empty:
            return 0

        self._write(features, target_date)
        logger.info(f"[FloodFeatures] wrote {len(features)} cells for {target_date}")
        return len(features)

    def compute_features(self, obs: pd.DataFrame) -> pd.DataFrame:
        """
        Public so it can be called in tests with a mock DataFrame.
        Input: raw observations DataFrame (h3_cell, source_provider, observed_at, raw_value)
        Output: wide feature DataFrame, one row per h3_cell
        """
        latest = self._latest_per_provider(obs)

        # Rename raw provider columns to feature names
        latest = latest.rename(columns={
            "sentinel1_sar_grd": "sar_backscatter_db",
            "era5_total_runoff": "glofas_discharge_m3s",
            "era5_soil_moisture_l1": "soil_saturation_index",
        })

        # Ensure columns exist even if that provider had no data
        for col in ["sar_backscatter_db", "glofas_discharge_m3s", "soil_saturation_index"]:
            if col not in latest.columns:
                latest[col] = None

        # 7-day precipitation sum: m → mm
        precip = (
            obs[obs["source_provider"] == "era5_total_precipitation"]
            .groupby("h3_cell")["raw_value"]
            .sum()
            .rename("precipitation_7d_mm") * 1000.0
        ).reset_index()
        latest = latest.merge(precip, on="h3_cell", how="left")

        # Backscatter anomaly: latest - 7-day mean (negative = recent drop = possible flood)
        sar_obs = obs[obs["source_provider"] == "sentinel1_sar_grd"]
        if not sar_obs.empty:
            sar_mean = (
                sar_obs.groupby("h3_cell")["raw_value"]
                .mean()
                .rename("_sar_mean")
            )
            latest = latest.merge(sar_mean, on="h3_cell", how="left")
            latest["backscatter_anomaly_7d"] = (
                latest["sar_backscatter_db"] - latest["_sar_mean"]
            )
            latest.drop(columns=["_sar_mean"], inplace=True)
        else:
            latest["backscatter_anomaly_7d"] = None

        # Drop the raw precip column if it came through from latest_per_provider
        latest.drop(columns=["era5_total_precipitation"], errors="ignore", inplace=True)

        return latest

    def _write(self, features: pd.DataFrame, target_date: date) -> None:
        observed_at = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        records = [
            MLFeatureFlood(
                h3_cell=row["h3_cell"],
                observed_at=observed_at,
                sar_backscatter_db=_nullable(row, "sar_backscatter_db"),
                backscatter_anomaly_7d=_nullable(row, "backscatter_anomaly_7d"),
                glofas_discharge_m3s=_nullable(row, "glofas_discharge_m3s"),
                soil_saturation_index=_nullable(row, "soil_saturation_index"),
                precipitation_7d_mm=_nullable(row, "precipitation_7d_mm"),
            )
            for _, row in features.iterrows()
        ]

        with get_session() as session:
            session.add_all(records)


def _nullable(row: pd.Series, col: str):
    val = row.get(col)
    if val is None:
        return None
    try:
        import math
        return None if math.isnan(float(val)) else float(val)
    except (TypeError, ValueError):
        return None
