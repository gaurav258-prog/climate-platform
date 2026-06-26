"""
Wildfire feature extractor.

Sources joined per H3 cell:
  nasa_firms_viirs       → fire radiative power (MW) — active fire detection
  era5_wind_u10          → eastward wind at 10m (m/s)
  era5_wind_v10          → northward wind at 10m (m/s)
  era5_2m_temperature    → 2m air temperature (K)
  era5_dewpoint_2m       → 2m dewpoint temperature (K)
  era5_total_precipitation → daily precipitation (m)

Derived features:
  gfs_wind_speed_ms      — √(u₁₀² + v₁₀²)
  gfs_relative_humidity_pct — Magnus formula from T₂ₘ and Td₂ₘ
  days_since_last_rain   — consecutive dry days (precip < 0.1mm/day)

Static features (effis_fire_weather_index, ndvi_index, ndvi_anomaly_vs_baseline)
are NULL until EFFIS and Sentinel-2 NDVI data are loaded.
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from core.db.models import MLFeatureWildfire
from core.db.session import get_session
from .base import BaseFeatureExtractor

logger = logging.getLogger(__name__)

RAIN_THRESHOLD_MM = 0.1  # days with <0.1mm counted as dry

SOURCES = [
    "nasa_firms_viirs",
    "era5_wind_u10",
    "era5_wind_v10",
    "era5_2m_temperature",
    "era5_dewpoint_2m",
    "era5_total_precipitation",
]


class WildfireFeatureExtractor(BaseFeatureExtractor):

    def extract(self, target_date: date) -> int:
        obs = self._fetch_observations(SOURCES, target_date, lookback_days=30)

        if obs.empty:
            logger.info(f"[WildfireFeatures] no observations for {target_date} — skipping")
            return 0

        features = self.compute_features(obs)
        if features.empty:
            return 0

        self._write(features, target_date)
        logger.info(f"[WildfireFeatures] wrote {len(features)} cells for {target_date}")
        return len(features)

    def compute_features(self, obs: pd.DataFrame) -> pd.DataFrame:
        latest = self._latest_per_provider(obs)

        latest = latest.rename(columns={
            "nasa_firms_viirs": "firms_frp_mw",
            "era5_wind_u10": "_u10",
            "era5_wind_v10": "_v10",
            "era5_2m_temperature": "_t2m_k",
            "era5_dewpoint_2m": "_d2m_k",
        })

        for col in ["firms_frp_mw", "_u10", "_v10", "_t2m_k", "_d2m_k"]:
            if col not in latest.columns:
                latest[col] = None

        # Wind speed: √(u² + v²)
        latest["gfs_wind_speed_ms"] = latest.apply(
            lambda r: wind_speed(r.get("_u10"), r.get("_v10")), axis=1
        )

        # Relative humidity from Magnus formula
        latest["gfs_relative_humidity_pct"] = latest.apply(
            lambda r: relative_humidity(r.get("_t2m_k"), r.get("_d2m_k")), axis=1
        )

        # Days since last rain in the lookback window
        precip_obs = obs[obs["source_provider"] == "era5_total_precipitation"].copy()
        if not precip_obs.empty:
            dry_days = _days_since_last_rain(precip_obs, RAIN_THRESHOLD_MM)
            latest = latest.merge(dry_days, on="h3_cell", how="left")
        else:
            latest["days_since_last_rain"] = None

        latest.drop(columns=["_u10", "_v10", "_t2m_k", "_d2m_k",
                              "era5_total_precipitation"], errors="ignore", inplace=True)
        return latest

    def _write(self, features: pd.DataFrame, target_date: date) -> None:
        observed_at = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        records = [
            MLFeatureWildfire(
                h3_cell=row["h3_cell"],
                observed_at=observed_at,
                firms_frp_mw=_nullable(row, "firms_frp_mw"),
                gfs_wind_speed_ms=_nullable(row, "gfs_wind_speed_ms"),
                gfs_relative_humidity_pct=_nullable(row, "gfs_relative_humidity_pct"),
                days_since_last_rain=int(row["days_since_last_rain"]) if pd.notna(row.get("days_since_last_rain")) else None,
            )
            for _, row in features.iterrows()
        ]

        with get_session() as session:
            session.add_all(records)


# ── pure functions (testable without DB) ─────────────────────────────────────

def wind_speed(u: float | None, v: float | None) -> float | None:
    if u is None or v is None:
        return None
    try:
        return math.sqrt(float(u) ** 2 + float(v) ** 2)
    except (TypeError, ValueError):
        return None


def relative_humidity(t2m_k: float | None, d2m_k: float | None) -> float | None:
    """
    Relative humidity (%) from 2m temperature and dewpoint in Kelvin.
    Uses Magnus formula constants from Alduchov & Eskridge (1996).
    """
    if t2m_k is None or d2m_k is None:
        return None
    try:
        t = float(t2m_k) - 273.15
        td = float(d2m_k) - 273.15
        a, b = 17.625, 243.04
        rh = 100.0 * math.exp(a * td / (b + td)) / math.exp(a * t / (b + t))
        return max(0.0, min(100.0, rh))  # clamp to valid range
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _days_since_last_rain(precip_obs: pd.DataFrame, threshold_mm: float) -> pd.DataFrame:
    """
    For each H3 cell, count consecutive dry days ending at the most recent observation.
    A day is dry if daily total precipitation < threshold_mm (default 0.1mm).
    """
    precip_obs = precip_obs.copy()
    precip_obs["date"] = precip_obs["observed_at"].dt.date

    # Daily total per cell (m → mm)
    daily = (
        precip_obs.groupby(["h3_cell", "date"])["raw_value"]
        .sum() * 1000.0
    ).reset_index().rename(columns={"raw_value": "precip_mm"})

    results = []
    for cell, cell_df in daily.groupby("h3_cell"):
        sorted_days = cell_df.sort_values("date", ascending=False)
        dry_count = 0
        for _, day_row in sorted_days.iterrows():
            if day_row["precip_mm"] < threshold_mm:
                dry_count += 1
            else:
                break
        results.append({"h3_cell": cell, "days_since_last_rain": dry_count})

    return pd.DataFrame(results)


def _nullable(row: pd.Series, col: str):
    val = row.get(col)
    if val is None:
        return None
    try:
        return None if math.isnan(float(val)) else float(val)
    except (TypeError, ValueError):
        return None
