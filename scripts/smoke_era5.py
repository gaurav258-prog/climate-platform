"""One-off smoke test: confirm an authenticated ERA5-Land download completes for the
West-Africa cocoa belt. Small request (2 vars, 1 day, 1 time). Not part of the pipeline."""
import logging
import tempfile
import time

import cdsapi
import numpy as np
import xarray as xr

from core.config import settings
from services.ingestion.regions import get_region

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

r = get_region("west_africa_cocoa")
print(f"smoke: ERA5-Land 2m_temp+precip, 2024-06-15 12:00, area {r.cds_area}", flush=True)
t0 = time.time()
c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False); tmp.close()
c.retrieve("reanalysis-era5-land", {
    "variable": ["2m_temperature", "total_precipitation"],
    "year": "2024", "month": "06", "day": ["15"], "time": ["12:00"],
    "area": r.cds_area, "format": "netcdf",
}, tmp.name)
dt = time.time() - t0
ds = xr.open_dataset(tmp.name)
print(f"DOWNLOAD OK in {dt:.0f}s | vars={list(ds.data_vars)} | dims={dict(ds.dims)}", flush=True)
print("t2m mean over cocoa belt (°C):", round(float(np.nanmean(ds['t2m'].values)) - 273.15, 1), flush=True)
print("grid cells:", int(ds['t2m'].size), flush=True)
