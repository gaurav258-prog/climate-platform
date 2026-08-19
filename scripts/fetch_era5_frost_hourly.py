"""
Fetch RAW HOURLY ERA5 2m temperature for a region's frost season, and derive the
daily minimum ourselves — replaces fetch_era5_frost.py's use of CDS's
`derived-era5-single-levels-daily-statistics` dataset, which ECMWF has flagged:
"An issue with the following parameters has been identified:
 minimum_2m_temperature_since_previous_post_processing ... should not be used."
(confirmed live, 2026-07-09 — see /tmp or CHANGELOG; the warning names exactly the
daily_minimum statistic frost scoring needs).

Root-cause fix, not a workaround: pull the STANDARD `reanalysis-era5-single-levels`
hourly archive (unaffected by that post-processing bug — it IS the raw model output,
not a derived statistic) and compute the daily minimum client-side. Downstream
(ml/features/frost.py) consumes the same "daily minimum 2m temperature" signal either
way; only where that number is computed has changed.

Usage: .venv/bin/python scripts/fetch_era5_frost_hourly.py brazil_coffee 1991 2024 [months]
       .venv/bin/python scripts/fetch_era5_frost_hourly.py smoke        # 1-month format test
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
FROST_MONTHS = ["05", "06", "07", "08", "09"]  # Brazil frost season (late autumn-winter)


def _fetch_one_year(c, r, region_key, year, months, out):
    print(f"frost HOURLY fetch: {region_key} yr={year} months={months} area {r.cds_area} → {out}", flush=True)
    t0 = time.time()
    # night-time frost matters most around 00-09 UTC for Brazil (UTC-3/-4) -- but request the
    # full day, cheap at this small a region, so the daily-min computed locally is exact, not
    # an approximation from a partial-day sample.
    c.retrieve("reanalysis-era5-single-levels", {
        "product_type": "reanalysis",
        "variable": ["2m_temperature"],
        "year": [str(year)], "month": months, "day": [f"{d:02d}" for d in range(1, 32)],
        "time": [f"{h:02d}:00" for h in range(24)],
        "area": r.cds_area,
        "data_format": "netcdf",
        "download_format": "unarchived",
    }, out)
    if zipfile.is_zipfile(out):
        with zipfile.ZipFile(out) as zf:
            nc = [n for n in zf.namelist() if n.endswith(".nc")]
            if nc:
                ex = out + "_d.nc"
                with zf.open(nc[0]) as s_, open(ex, "wb") as d_:
                    shutil.copyfileobj(s_, d_)
                os.replace(ex, out)
    print(f"FROST HOURLY OK yr={year} in {time.time()-t0:.0f}s → {out} ({os.path.getsize(out)/1e6:.1f} MB)", flush=True)


def fetch(region_key, y0, y1, months=FROST_MONTHS, smoke=False):
    """One CDS request PER YEAR -- a single multi-decade request exceeds CDS's per-request
    cost limit ('Your request is too large, please reduce your selection', confirmed live
    2026-07-09 against a 34-year x 5-month x 24-hour request). Each year lands as its own
    file under OUT_DIR/frost_hourly_years/; downstream code opens them with
    xr.open_mfdataset. Idempotent per year -- re-running skips years already on disk."""
    r = get_region(region_key)
    if smoke:
        os.makedirs(OUT_DIR, exist_ok=True)
        out = os.path.join(OUT_DIR, f"{region_key}_frost_hourly_smoke.nc")
        c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
        _fetch_one_year(c, r, region_key, 2021, ["07"], out)
        return [out]

    year_dir = os.path.join(OUT_DIR, "frost_hourly_years")
    os.makedirs(year_dir, exist_ok=True)
    c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
    outs = []
    for year in range(y0, y1 + 1):
        out = os.path.join(year_dir, f"{region_key}_{year}.nc")
        outs.append(out)
        if os.path.exists(out) and os.path.getsize(out) > 0:
            print(f"skip yr={year} (already fetched) → {out}", flush=True)
            continue
        _fetch_one_year(c, r, region_key, year, months, out)
    print(f"FROST HOURLY ALL YEARS OK → {len(outs)} files in {year_dir}", flush=True)
    return outs


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "smoke":
        fetch("brazil_coffee", 2021, 2021, smoke=True)
    else:
        region = sys.argv[1] if len(sys.argv) > 1 else "brazil_coffee"
        y0 = int(sys.argv[2]) if len(sys.argv) > 2 else 1991
        y1 = int(sys.argv[3]) if len(sys.argv) > 3 else 2024
        fetch(region, y0, y1)
