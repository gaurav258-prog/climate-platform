"""
Heat feature extractor.

Sources joined per H3 cell:
  sentinel3_slstr_lst    → land surface temperature (K)
  era5_2m_temperature    → 2m air temperature (K)
  era5_dewpoint_2m       → 2m dewpoint temperature (K)

Derived features:
  era5_temp_2m_c         — air temperature in Celsius (K − 273.15)
  days_above_35c_ytd     — days in the observation window with T > 35°C

Static baseline features (lst_anomaly_vs_baseline, era5_temp_30yr_mean,
era5_temp_trend_per_decade, urban_heat_island_factor, population_density)
are NULL until the ERA5 30-year historical load is complete.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pandas as pd

from core.db.models import MLFeatureHeat
from core.db.session import get_session
from .base import BaseFeatureExtractor

logger = logging.getLogger(__name__)

KELVIN_OFFSET = 273.15
HEAT_THRESHOLD_K = 35.0 + KELVIN_OFFSET  # 35°C in Kelvin

SOURCES = [
    "sentinel3_slstr_lst",
    "era5_2m_temperature",
    "era5_dewpoint_2m",
]


class HeatFeatureExtractor(BaseFeatureExtractor):

    def extract(self, target_date: date) -> int:
        obs = self._fetch_observations(SOURCES, target_date, lookback_days=30)

        if obs.empty:
            logger.info(f"[HeatFeatures] no observations for {target_date} — skipping")
            return 0

        features = self.compute_features(obs)
        if features.empty:
            return 0

        self._write(features, target_date)
        logger.info(f"[HeatFeatures] wrote {len(features)} cells for {target_date}")
        return len(features)

    def compute_features(self, obs: pd.DataFrame) -> pd.DataFrame:
        latest = self._latest_per_provider(obs)

        latest = latest.rename(columns={
            "sentinel3_slstr_lst": "lst_kelvin",
            "era5_2m_temperature": "_t2m_k",
            "era5_dewpoint_2m": "_d2m_k",
        })

        for col in ["lst_kelvin", "_t2m_k", "_d2m_k"]:
            if col not in latest.columns:
                latest[col] = None

        # Air temperature in Celsius
        latest["era5_temp_2m_c"] = latest["_t2m_k"].apply(
            lambda k: (float(k) - KELVIN_OFFSET) if pd.notna(k) else None
        )

        # Days above 35°C in the lookback window
        t2m_obs = obs[obs["source_provider"] == "era5_2m_temperature"].copy()
        if not t2m_obs.empty:
            t2m_obs["date"] = t2m_obs["observed_at"].dt.date
            hot_days = (
                t2m_obs.groupby(["h3_cell", "date"])["raw_value"]
                .max()
                .gt(HEAT_THRESHOLD_K)
                .groupby("h3_cell")
                .sum()
                .astype(int)
                .rename("days_above_35c_ytd")
                .reset_index()
            )
            latest = latest.merge(hot_days, on="h3_cell", how="left")
            latest["days_above_35c_ytd"] = latest["days_above_35c_ytd"].fillna(0).astype(int)
        else:
            latest["days_above_35c_ytd"] = None

        latest.drop(columns=["_t2m_k", "_d2m_k"], errors="ignore", inplace=True)
        return latest

    def _write(self, features: pd.DataFrame, target_date: date) -> None:
        observed_at = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        records = [
            MLFeatureHeat(
                h3_cell=row["h3_cell"],
                observed_at=observed_at,
                lst_kelvin=_nullable(row, "lst_kelvin"),
                era5_temp_2m_c=_nullable(row, "era5_temp_2m_c"),
                days_above_35c_ytd=int(row["days_above_35c_ytd"]) if pd.notna(row.get("days_above_35c_ytd")) else None,
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
