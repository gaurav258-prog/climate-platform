"""
Fetch ERA5 DAILY-MINIMUM 2m temperature for a region's frost season — the daily extreme
that monthly means miss (the Jul-2021 Brazil coffee frost). Uses the CDS derived daily-
statistics dataset (daily_minimum). Small vs the hourly archive.

Usage: .venv/bin/python scripts/fetch_era5_frost.py brazil_coffee 1991 2024 [months]
       .venv/bin/python scripts/fetch_era5_frost.py smoke        # 1-month format test
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
FROST_MONTHS = ["05", "06", "07", "08", "09"]  # Brazil frost season (late autumn–winter)


def fetch(region_key, y0, y1, months=FROST_MONTHS, smoke=False):
    r = get_region(region_key)
    os.makedirs(OUT_DIR, exist_ok=True)
    years = ["2021"] if smoke else [str(y) for y in range(y0, y1 + 1)]
    mo = ["07"] if smoke else months
    out = os.path.join(OUT_DIR, f"{region_key}_frost_{'smoke' if smoke else str(y0)+'_'+str(y1)}.nc")
    print(f"frost fetch: {region_key} yrs={len(years)} months={mo} area {r.cds_area} → {out}", flush=True)
    c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
    t0 = time.time()
    c.retrieve("derived-era5-single-levels-daily-statistics", {
        "product_type": "reanalysis",
        "variable": ["2m_temperature"],
        "year": years, "month": mo, "day": [f"{d:02d}" for d in range(1, 32)],
        "daily_statistic": "daily_minimum",
        "time_zone": "utc+00:00",
        "frequency": "1_hourly",
        "area": r.cds_area,
    }, out)
    if zipfile.is_zipfile(out):
        with zipfile.ZipFile(out) as zf:
            nc = [n for n in zf.namelist() if n.endswith(".nc")]
            if nc:
                ex = out + "_d.nc"
                with zf.open(nc[0]) as s_, open(ex, "wb") as d_:
                    shutil.copyfileobj(s_, d_)
                os.replace(ex, out)
    print(f"FROST OK in {time.time()-t0:.0f}s → {out} ({os.path.getsize(out)/1e6:.1f} MB)", flush=True)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        fetch("brazil_coffee", 2021, 2021, smoke=True)
    else:
        region = sys.argv[1] if len(sys.argv) > 1 else "brazil_coffee"
        y0 = int(sys.argv[2]) if len(sys.argv) > 2 else 1991
        y1 = int(sys.argv[3]) if len(sys.argv) > 3 else 2024
        fetch(region, y0, y1)
