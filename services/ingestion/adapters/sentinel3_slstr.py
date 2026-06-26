"""
Sentinel-3 SLSTR (Sea and Land Surface Temperature Radiometer) adapter — CDSE.

Land Surface Temperature (LST) in Kelvin is the primary heat stress signal.
LST anomaly vs 30-year ERA5 baseline is the key model feature.

Production flow (DIAS compute):
  1. Search CDSE for S3 SL_2_LST___ products over EU for target date
  2. Download (typically 300–500 MB per orbit pass)
  3. Extract LST_in (in-situ surface temperature) band
  4. Mask cloud-contaminated pixels (quality flag)
  5. Reproject and aggregate to H3 resolution-8 cells
  6. Write observations

Local dev: set SENTINEL3_STUB=true to use fixture data.

Register at https://dataspace.copernicus.eu/
"""
import csv
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

from core.config import settings
from core.db.models import SatelliteObservation
from core.types import HazardType
from .base import BaseAdapter, ADAPTER_VERSION

logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu"
    "/auth/realms/CDSE/protocol/openid-connect/token"
)
CDSE_SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
EU_WKT = "POLYGON((-10 35, 30 35, 30 72, -10 72, -10 35))"

STUB_FIXTURE = Path(__file__).parent.parent.parent.parent / "tests/fixtures/sample_slstr_features.csv"


class Sentinel3SLSTRAdapter(BaseAdapter):
    source_provider = "sentinel3_slstr_lst"

    def __init__(self, target_date: Optional[date] = None):
        self.target_date = target_date or (date.today() - timedelta(days=1))
        self.stub = os.getenv("SENTINEL3_STUB", "false").lower() == "true"

    def fetch(self) -> list[dict]:
        if self.stub:
            logger.info("[S3-SLSTR] stub mode — returning fixture data")
            return [{"stub": True}]

        if not settings.COPERNICUS_USER or not settings.COPERNICUS_PASSWORD:
            logger.warning(
                "[S3-SLSTR] COPERNICUS_USER / COPERNICUS_PASSWORD not set. "
                "Set SENTINEL3_STUB=true for local dev."
            )
            return []

        token = self._get_access_token()
        if not token:
            return []

        products = self._search_products(token)
        logger.info(f"[S3-SLSTR] found {len(products)} SLSTR LST products for {self.target_date}")
        return [{"product_id": p["Id"], "product_name": p["Name"]} for p in products]

    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        if not raw:
            return []

        if raw[0].get("stub"):
            return self._stub_observations()

        # TODO Sprint 3: download + extract LST band + reproject to H3
        logger.info("[S3-SLSTR] scene processing not yet implemented — returning empty (Sprint 3)")
        return []

    def _stub_observations(self) -> list[SatelliteObservation]:
        if not STUB_FIXTURE.exists():
            logger.warning(f"[S3-SLSTR] fixture not found: {STUB_FIXTURE}")
            return []

        observations = []
        observed_at = datetime.combine(self.target_date, datetime.min.time()).replace(tzinfo=timezone.utc)

        with open(STUB_FIXTURE) as f:
            for row in csv.DictReader(f):
                try:
                    observations.append(SatelliteObservation(
                        h3_cell=row["h3_cell"],
                        h3_resolution=settings.H3_RESOLUTION,
                        source_provider=self.source_provider,
                        hazard_type=HazardType.HEAT_ACUTE.value,
                        observed_at=observed_at,
                        raw_value=float(row["lst_kelvin"]),
                        raw_unit="K",
                        quality_flag=int(row.get("quality_flag", 0)),
                        adapter_version=ADAPTER_VERSION,
                    ))
                except (ValueError, KeyError) as exc:
                    logger.warning(f"[S3-SLSTR] skipping malformed stub row: {exc}")

        logger.info(f"[S3-SLSTR] stub: returned {len(observations)} synthetic observations")
        return observations

    def _get_access_token(self) -> Optional[str]:
        try:
            resp = httpx.post(
                CDSE_TOKEN_URL,
                data={
                    "client_id": "cdse-public",
                    "username": settings.COPERNICUS_USER,
                    "password": settings.COPERNICUS_PASSWORD,
                    "grant_type": "password",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["access_token"]
        except Exception as exc:
            logger.error(f"[S3-SLSTR] CDSE authentication failed: {exc}")
            return None

    def _search_products(self, token: str) -> list[dict]:
        d = self.target_date
        start = f"{d.isoformat()}T00:00:00Z"
        end = f"{d.isoformat()}T23:59:59Z"

        filter_expr = (
            "Collection/Name eq 'SENTINEL-3' and "
            "Attributes/OData.CSC.StringAttribute/any("
            "  att:att/Name eq 'productType' and "
            "  att/OData.CSC.StringAttribute/Value eq 'SL_2_LST___') and "
            f"ContentDate/Start gt {start} and "
            f"ContentDate/Start lt {end} and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;{EU_WKT}')"
        )

        try:
            resp = httpx.get(
                CDSE_SEARCH_URL,
                params={"$filter": filter_expr, "$orderby": "ContentDate/Start asc", "$top": 50},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("value", [])
        except Exception as exc:
            logger.error(f"[S3-SLSTR] CDSE search failed: {exc}")
            return []
