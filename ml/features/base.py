"""
Abstract base for feature extractors.

Each extractor:
  - reads from satellite_observations (written by ingestion adapters)
  - computes derived features (anomalies, ratios, unit conversions)
  - writes to its ml_features_{hazard} table

No ML code here — just data joining and engineering.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import text

from core.db.session import get_session

logger = logging.getLogger(__name__)


class BaseFeatureExtractor(ABC):

    @abstractmethod
    def extract(self, target_date: date) -> int:
        """Extract features for one day. Returns number of H3 cells written."""

    def _fetch_observations(
        self,
        source_providers: list[str],
        target_date: date,
        lookback_days: int = 7,
        max_quality_flag: int = 0,
    ) -> pd.DataFrame:
        """
        Fetch satellite observations from the past N days for the given providers.
        Returns DataFrame with columns: h3_cell, source_provider, observed_at, raw_value
        """
        end_dt = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
        start_dt = end_dt - timedelta(days=lookback_days)

        sql = text("""
            SELECT h3_cell, source_provider, observed_at, CAST(raw_value AS FLOAT) AS raw_value
            FROM satellite_observations
            WHERE source_provider = ANY(:providers)
              AND quality_flag <= :max_quality_flag
              AND observed_at BETWEEN :start_dt AND :end_dt
            ORDER BY h3_cell, source_provider, observed_at
        """)

        with get_session() as session:
            result = session.execute(sql, {
                "providers": source_providers,
                "max_quality_flag": max_quality_flag,
                "start_dt": start_dt,
                "end_dt": end_dt,
            })
            rows = result.mappings().all()

        if not rows:
            return pd.DataFrame(
                columns=["h3_cell", "source_provider", "observed_at", "raw_value"]
            )

        return pd.DataFrame([dict(r) for r in rows])

    @staticmethod
    def _latest_per_provider(obs: pd.DataFrame) -> pd.DataFrame:
        """
        For each (h3_cell, source_provider), keep the most recent raw_value.
        Returns a wide DataFrame: one row per h3_cell, one column per source_provider.
        """
        latest = (
            obs.sort_values("observed_at")
            .groupby(["h3_cell", "source_provider"])["raw_value"]
            .last()
            .unstack("source_provider")
            .reset_index()
        )
        return latest
