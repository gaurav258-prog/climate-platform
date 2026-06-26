"""
Sentinel-1 SAR (C-band, GRD) adapter — Copernicus Data Space Ecosystem (CDSE).

SAR backscatter in VV polarisation is the primary flood detection signal:
open water returns near-zero backscatter (<-20 dB), while dry land is
typically -8 to -5 dB. A sudden drop in a cell signals inundation.

Production flow (runs on DIAS compute, not locally):
  1. Search CDSE catalogue for GRD products over EU for target date
  2. Download scene (~800 MB each) to DIAS object storage
  3. Process with ESA SNAP: orbit → noise → calibrate → terrain correct → dB
  4. Export COG derivative (40 MB) → extract H3 backscatter means
  5. Write SatelliteObservation rows + store COG URI

Local dev / CI: set SENTINEL1_STUB=true in .env to return synthetic
backscatter from tests/fixtures/sample_sar_features.csv instead.

Register at https://dataspace.copernicus.eu/ — free account.
Add to .env:
    COPERNICUS_USER=<your-email>
    COPERNICUS_PASSWORD=<your-password>
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
CDSE_SEARCH_URL = (
    "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
)

# EU bounding box as WKT polygon for CDSE OData filter
EU_WKT = "POLYGON((-10 35, 30 35, 30 72, -10 72, -10 35))"

STUB_FIXTURE = Path(__file__).parent.parent.parent.parent / "tests/fixtures/sample_sar_features.csv"


class Sentinel1SARAdapter(BaseAdapter):
    source_provider = "sentinel1_sar_grd"

    def __init__(self, target_date: Optional[date] = None):
        self.target_date = target_date or (date.today() - timedelta(days=1))
        self.stub = os.getenv("SENTINEL1_STUB", "false").lower() == "true"

    def fetch(self) -> list[dict]:
        if self.stub:
            logger.info("[S1-SAR] stub mode — returning fixture data")
            return [{"stub": True}]

        if not settings.COPERNICUS_USER or not settings.COPERNICUS_PASSWORD:
            logger.warning(
                "[S1-SAR] COPERNICUS_USER / COPERNICUS_PASSWORD not set. "
                "Set SENTINEL1_STUB=true for local dev."
            )
            return []

        token = self._get_access_token()
        if not token:
            return []

        products = self._search_products(token)
        logger.info(f"[S1-SAR] found {len(products)} Sentinel-1 GRD products for {self.target_date}")

        # In production: download + SNAP process on DIAS, return processed COG paths
        # For now: return product metadata only (SNAP processing not yet implemented)
        return [{"product_id": p["Id"], "product_name": p["Name"]} for p in products]

    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        if not raw:
            return []

        if raw[0].get("stub"):
            return self._stub_observations()

        # TODO Sprint 3: implement SNAP processing on DIAS
        # For each product_id: download → process → extract H3 backscatter → return observations
        logger.info("[S1-SAR] SNAP processing not yet implemented — returning empty (Sprint 3)")
        return []

    def _stub_observations(self) -> list[SatelliteObservation]:
        """Return synthetic SAR observations from fixture CSV for local testing."""
        if not STUB_FIXTURE.exists():
            logger.warning(f"[S1-SAR] fixture not found: {STUB_FIXTURE}")
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
                        hazard_type=HazardType.FLOOD.value,
                        observed_at=observed_at,
                        raw_value=float(row["backscatter_db"]),
                        raw_unit="dB",
                        quality_flag=0,
                        adapter_version=ADAPTER_VERSION,
                    ))
                except (ValueError, KeyError) as exc:
                    logger.warning(f"[S1-SAR] skipping malformed stub row: {exc}")

        logger.info(f"[S1-SAR] stub: returned {len(observations)} synthetic observations")
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
            logger.error(f"[S1-SAR] CDSE authentication failed: {exc}")
            return None

    def _search_products(self, token: str) -> list[dict]:
        d = self.target_date
        start = f"{d.isoformat()}T00:00:00Z"
        end = f"{d.isoformat()}T23:59:59Z"

        filter_expr = (
            "Collection/Name eq 'SENTINEL-1' and "
            "Attributes/OData.CSC.StringAttribute/any("
            "  att:att/Name eq 'productType' and "
            "  att/OData.CSC.StringAttribute/Value eq 'GRD') and "
            f"ContentDate/Start gt {start} and "
            f"ContentDate/Start lt {end} and "
            f"OData.CSC.Intersects(area=geography'SRID=4326;{EU_WKT}')"
        )

        try:
            resp = httpx.get(
                CDSE_SEARCH_URL,
                params={"$filter": filter_expr, "$orderby": "ContentDate/Start asc", "$top": 100},
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("value", [])
        except Exception as exc:
            logger.error(f"[S1-SAR] CDSE search failed: {exc}")
            return []
