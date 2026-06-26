"""
ERA5-Land daily reanalysis adapter — Copernicus Climate Data Store (CDS).

Provides: 2m temperature, total precipitation, soil moisture, wind components, dewpoint.
Coverage: EU bounding box [N=72, W=-10, S=35, E=30] at 0.1° resolution.
Cadence: daily (ERA5 data is available ~5 days behind real time).

Register at https://cds.climate.copernicus.eu/ — free account.
Add to .env:
    CDSAPI_URL=https://cds.climate.copernicus.eu/api
    CDSAPI_KEY=<uid>:<api-key>
"""
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import xarray as xr

from core.config import settings
from core.db.models import SatelliteObservation
from core.netcdf_utils import xarray_to_h3_dataframe
from core.types import HazardType
from .base import BaseAdapter, ADAPTER_VERSION

logger = logging.getLogger(__name__)

# ERA5-Land variable name → (short name in NetCDF, hazard type, unit, source_provider tag)
ERA5_VARIABLES = {
    "2m_temperature": {
        "nc_var": "t2m",
        "hazard_type": HazardType.HEAT_ACUTE.value,
        "unit": "K",
        "tag": "era5_2m_temperature",
    },
    "total_precipitation": {
        "nc_var": "tp",
        "hazard_type": HazardType.FLOOD.value,
        "unit": "m",
        "tag": "era5_total_precipitation",
    },
    "volumetric_soil_water_layer_1": {
        "nc_var": "swvl1",
        "hazard_type": HazardType.FLOOD.value,
        "unit": "m3_m-3",
        "tag": "era5_soil_moisture_l1",
    },
    "10m_u_component_of_wind": {
        "nc_var": "u10",
        "hazard_type": HazardType.WILDFIRE.value,
        "unit": "m_s-1",
        "tag": "era5_wind_u10",
    },
    "10m_v_component_of_wind": {
        "nc_var": "v10",
        "hazard_type": HazardType.WILDFIRE.value,
        "unit": "m_s-1",
        "tag": "era5_wind_v10",
    },
    "2m_dewpoint_temperature": {
        "nc_var": "d2m",
        "hazard_type": HazardType.HEAT_ACUTE.value,
        "unit": "K",
        "tag": "era5_dewpoint_2m",
    },
}

EU_AREA = [72, -10, 35, 30]  # [N, W, S, E] — CDS order


class ERA5Adapter(BaseAdapter):
    source_provider = "era5_land"

    def __init__(self, target_date: Optional[date] = None):
        # ERA5 lags ~5 days; default to 7 days ago to be safe
        self.target_date = target_date or (date.today() - timedelta(days=7))

    def fetch(self) -> list[dict]:
        if not settings.CDSAPI_KEY:
            logger.warning("CDSAPI_KEY not set — skipping ERA5. Add it to .env to enable.")
            return []

        import cdsapi
        client = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=True)
        d = self.target_date

        # Fetch all 6 variables in ONE CDS request → one queue wait instead of six.
        # CDS returns a single multi-variable NetCDF (or ZIP containing it).
        all_cds_vars = list(ERA5_VARIABLES.keys())
        logger.info(f"[ERA5] fetching {len(all_cds_vars)} variables for {d} (batch)")

        tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
        tmp.close()

        try:
            client.retrieve(
                "reanalysis-era5-land",
                {
                    "variable": all_cds_vars,
                    "year": str(d.year),
                    "month": f"{d.month:02d}",
                    "day": [f"{d.day:02d}"],
                    "time": ["00:00", "06:00", "12:00", "18:00"],
                    "area": EU_AREA,
                    "format": "netcdf",
                },
                tmp.name,
            )
            return [{"file": tmp.name, "batch": True}]
        except Exception as exc:
            logger.error(f"[ERA5] batch download failed: {exc}")
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)
            return []

    @staticmethod
    def _extract_if_zip(path: str) -> str:
        """CDS now returns ZIP archives. Extract the NetCDF inside and return its path."""
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

    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        if not raw:
            return []

        observations = []
        item = raw[0]
        path = self._extract_if_zip(item["file"])

        try:
            ds = xr.open_dataset(path)
            logger.info(f"[ERA5] opened batch NetCDF, vars: {list(ds.data_vars)}, dims: {dict(ds.dims)}")

            for cds_var, meta in ERA5_VARIABLES.items():
                nc_var = meta["nc_var"]
                if nc_var not in ds:
                    logger.warning(f"[ERA5] variable {nc_var} not in dataset — skipping")
                    continue

                df = xarray_to_h3_dataframe(ds, nc_var)
                for _, row in df.iterrows():
                    observations.append(SatelliteObservation(
                        h3_cell=row["h3_cell"],
                        h3_resolution=settings.H3_RESOLUTION,
                        source_provider=meta["tag"],
                        hazard_type=meta["hazard_type"],
                        observed_at=row["observed_at"].to_pydatetime().replace(tzinfo=timezone.utc),
                        raw_value=row["value"],
                        raw_unit=meta["unit"],
                        quality_flag=0,
                        adapter_version=ADAPTER_VERSION,
                    ))

            ds.close()

        except Exception as exc:
            logger.error(f"[ERA5] batch processing failed: {exc}")
        finally:
            if os.path.exists(path):
                os.unlink(path)

        return observations
