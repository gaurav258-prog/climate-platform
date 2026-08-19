"""
Fetch the ERA5-Land MONTHLY-means climatology needed for drought indices (SPI/SPEI),
scoped to one region. This is the correct, minimal version of the CDS "export": three
variables (not 57), one region box (not global), monthly means (not hourly).

  - total_precipitation   → SPI, precipitation deficit
  - 2m_temperature        → SPEI (temperature side), heat baseline
  - potential_evaporation → SPEI (water-balance = precip − PET)

Default 1991–2024 gives a >30-yr baseline (WMO standard normal 1991–2020 + recent years).
Writes one NetCDF per region to data/era5_baseline/. Run (needs CDSAPI_KEY, sandbox off):
    .venv/bin/python scripts/fetch_era5_baseline.py west_africa_cocoa 1991 2024
"""
import logging
import os
import shutil
import sys
import time
import zipfile

import cdsapi

from core.config import settings
from services.ingestion.regions import get_region

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

OUT_DIR = "data/era5_baseline"
VARIABLES = ["total_precipitation", "2m_temperature", "potential_evaporation"]


def fetch_baseline(region_key: str, y0: int, y1: int) -> str:
    r = get_region(region_key)
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, f"{region_key}_{y0}_{y1}_monthly.nc")
    years = [str(y) for y in range(y0, y1 + 1)]
    print(f"baseline: {region_key} {y0}-{y1}, {len(VARIABLES)} vars, area {r.cds_area} → {out}", flush=True)

    c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
    t0 = time.time()
    c.retrieve("reanalysis-era5-land-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": VARIABLES,
        "year": years,
        "month": [f"{m:02d}" for m in range(1, 13)],
        "time": ["00:00"],
        "area": r.cds_area,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }, out)
    # CDS sometimes returns a ZIP even when a .nc name is requested — extract if so.
    if zipfile.is_zipfile(out):
        with zipfile.ZipFile(out) as zf:
            nc = [n for n in zf.namelist() if n.endswith(".nc")]
            if nc:
                extracted = out + "_data.nc"
                with zf.open(nc[0]) as src, open(extracted, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                os.replace(extracted, out)
    print(f"BASELINE OK in {time.time()-t0:.0f}s → {out} ({os.path.getsize(out)/1e6:.1f} MB)", flush=True)
    return out


if __name__ == "__main__":
    region = sys.argv[1] if len(sys.argv) > 1 else "west_africa_cocoa"
    y0 = int(sys.argv[2]) if len(sys.argv) > 2 else 1991
    y1 = int(sys.argv[3]) if len(sys.argv) > 3 else 2024
    fetch_baseline(region, y0, y1)
