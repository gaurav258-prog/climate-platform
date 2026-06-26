"""
River runoff adapter — ERA5-Land via Copernicus Climate Data Store (CDS).

Provides: total runoff (surface + sub-surface) as the primary river discharge proxy.

Note: GloFAS reanalysis (`cems-glofas-reanalysis`) was removed from CDS in 2025.
ERA5-Land total runoff is the best available substitute on the same API:
  - Strong correlation with observed river discharge during flood events
  - Available back to 1950 — covers Rhine 2021 and Gironde 2022 validation periods
  - Same 0.1° resolution as other ERA5-Land variables

Future: true daily discharge can be added from EFAS (efas.eu) when that API
integration is scoped.

Requires same CDS credentials as ERA5Adapter:
    CDSAPI_URL=https://cds.climate.copernicus.eu/api
    CDSAPI_KEY=<personal-access-token>
"""
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import numpy as np
import xarray as xr

from core.config import settings
from core.db.models import SatelliteObservation
from core.netcdf_utils import xarray_to_h3_dataframe
from core.types import HazardType
from .base import BaseAdapter, ADAPTER_VERSION

logger = logging.getLogger(__name__)

EU_AREA = [72, -10, 35, 30]


class GloFASAdapter(BaseAdapter):
    """
    ERA5-Land total runoff — flood onset signal for EU river basins.
    Unit: m (metres of water equivalent per grid cell per day).
    Stored as source_provider='era5_total_runoff' to keep it distinct from GloFAS.
    """
    source_provider = "era5_total_runoff"

    def __init__(self, target_date: Optional[date] = None):
        self.target_date = target_date or (date.today() - timedelta(days=7))

    def fetch(self) -> list[dict]:
        if not settings.CDSAPI_KEY:
            logger.warning("[Runoff] CDSAPI_KEY not set — skipping.")
            return []

        import cdsapi
        client = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=True)
        d = self.target_date

        tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
        tmp.close()

        try:
            logger.info(f"[Runoff] fetching ERA5-Land total_runoff for {d}")
            client.retrieve(
                "reanalysis-era5-land",
                {
                    "variable": ["runoff"],
                    "year": str(d.year),
                    "month": f"{d.month:02d}",
                    "day": [f"{d.day:02d}"],
                    "time": ["00:00", "06:00", "12:00", "18:00"],
                    "area": EU_AREA,
                    "format": "netcdf",
                },
                tmp.name,
            )
            return [{"file": tmp.name}]
        except Exception as exc:
            logger.error(f"[Runoff] download failed: {exc}")
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            return []

    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        if not raw:
            return []

        path = self._extract_if_zip(raw[0]["file"])
        observations = []

        try:
            ds = xr.open_dataset(path)
            nc_var = "ro" if "ro" in ds else list(ds.data_vars)[0]
            logger.info(f"[Runoff] opened NetCDF, variable: {nc_var}, dims: {dict(ds.dims)}")

            df = xarray_to_h3_dataframe(ds, nc_var)
            ds.close()

            for _, row in df.iterrows():
                runoff = row["value"]
                if np.isnan(runoff) or runoff < 0:
                    continue

                observations.append(SatelliteObservation(
                    h3_cell=row["h3_cell"],
                    h3_resolution=settings.H3_RESOLUTION,
                    source_provider=self.source_provider,
                    hazard_type=HazardType.FLOOD.value,
                    observed_at=row["observed_at"].to_pydatetime().replace(tzinfo=timezone.utc),
                    raw_value=runoff,
                    raw_unit="m",
                    quality_flag=0,
                    adapter_version=ADAPTER_VERSION,
                ))

        except Exception as exc:
            logger.error(f"[Runoff] processing failed: {exc}")
        finally:
            if os.path.exists(path):
                os.unlink(path)

        return observations

    @staticmethod
    def _extract_if_zip(path: str) -> str:
        if not zipfile.is_zipfile(path):
            return path
        with zipfile.ZipFile(path) as zf:
            nc_names = [n for n in zf.namelist() if n.endswith(".nc")]
            if not nc_names:
                return path
            out = path + "_data.nc"
            with zf.open(nc_names[0]) as src, open(out, "wb") as dst:
                shutil.copyfileobj(src, dst)
        os.unlink(path)
        return out
