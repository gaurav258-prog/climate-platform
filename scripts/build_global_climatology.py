"""
Build the global 1991-2020 monthly climatology baseline (mean+std per grid cell
per calendar month, for 2m temperature and daily precipitation rate) — the
one-time data-engineering step that unlocks heat/drought on-demand scoring for
ANY point on Earth, not just the handful of regions already batch-processed.

Uses ECMWF's own pre-aggregated `reanalysis-era5-single-levels-monthly-means`
(confirmed live: ONE request, ~936MB, ~5min, no chunking needed) rather than
fetching 30 years of raw hourly/daily data ourselves — a meaningfully smaller
job than it first looks. See core/db/migrations/versions/
b3c4d5e6f7a8_climatology_baseline.py for the schema + full reasoning.

`total_precipitation` in this product is ECMWF's mean DAILY rate for that
calendar month (metres), not a monthly total — kept as mm/day so it stays
directly comparable to a live daily ERA5-Land reading, not a moving-target
"days-in-this-month" total.

The fetch is cached to disk (raw ERA5 zip) since it's the expensive, external
step; re-running this script re-aggregates from the cache instead of re-fetching.

Usage:  python scripts/build_global_climatology.py
"""
from __future__ import annotations

import os
import shutil
import time
import zipfile
from datetime import datetime, timezone

import h3
import numpy as np
import pandas as pd
import xarray as xr
from sqlalchemy import text

from core.db.session import get_session

RAW_CACHE = "data/era5_climatology_baseline/era5_monthly_means_1991_2020.zip"
BASELINE_PERIOD = "1991-2020"
YEARS = list(range(1991, 2021))
H3_RES = 8


def fetch() -> str:
    """One CDS request for 30 years x 12 months of global monthly-mean t2m + tp.
    Cached to RAW_CACHE — re-run reuses the cache instead of re-fetching ~936MB."""
    if os.path.exists(RAW_CACHE):
        print(f"[fetch] using cached {RAW_CACHE}")
        return RAW_CACHE
    import cdsapi
    os.makedirs(os.path.dirname(RAW_CACHE), exist_ok=True)
    c = cdsapi.Client(quiet=True)
    t0 = time.time()
    print(f"[fetch] requesting {YEARS[0]}-{YEARS[-1]}, global, 2 variables (no cache found)...")
    c.retrieve("reanalysis-era5-single-levels-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": ["2m_temperature", "total_precipitation"],
        "year": [str(y) for y in YEARS],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "time": ["00:00"],
        "format": "netcdf",
        "area": [90, -180, -90, 180],
    }, RAW_CACHE)
    print(f"[fetch] done in {time.time()-t0:.0f}s")
    return RAW_CACHE


def _extract(zip_path: str) -> tuple[xr.Dataset, xr.Dataset]:
    """ERA5 splits accumulated (precip) vs instantaneous (temp) variables into
    separate NetCDF files inside the zip (different GRIB stepType) — same kind
    of multi-file split CAMS's variable requests hit earlier in this project."""
    extract_dir = os.path.dirname(zip_path) + "/_extracted"
    os.makedirs(extract_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        zf.extractall(extract_dir)
    t2m_file = next(extract_dir + "/" + n for n in names if "avgua" in n or "instan" in n)
    tp_file = next(extract_dir + "/" + n for n in names if "avgad" in n or "accum" in n)
    ds_t2m = xr.open_dataset(t2m_file)
    ds_tp = xr.open_dataset(tp_file)
    return ds_t2m, ds_tp


def aggregate(ds_t2m: xr.Dataset, ds_tp: xr.Dataset) -> pd.DataFrame:
    """30 years x 12 months -> (mean, std) per grid cell per calendar month."""
    print("[aggregate] computing per-month mean/std across 30 years (xarray groupby)...")
    t2m_by_month = ds_t2m["t2m"].groupby("valid_time.month")
    tp_by_month = ds_tp["tp"].groupby("valid_time.month")

    t2m_mean = t2m_by_month.mean("valid_time")
    t2m_std = t2m_by_month.std("valid_time", ddof=1)
    tp_mean_m = tp_by_month.mean("valid_time")
    tp_std_m = tp_by_month.std("valid_time", ddof=1)

    lat = ds_t2m["latitude"].values
    lon = ds_t2m["longitude"].values
    print(f"[aggregate] grid: {len(lat)} x {len(lon)} = {len(lat)*len(lon)} cells x 12 months")

    print("[aggregate] converting grid centres to H3 cells (one pass, reused across all 12 months)...")
    h3_grid = np.empty((len(lat), len(lon)), dtype=object)
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            h3_grid[i, j] = h3.latlng_to_cell(float(la), float(lo), H3_RES)

    rows = []
    for month in range(1, 13):
        tm = t2m_mean.sel(month=month).values
        ts = t2m_std.sel(month=month).values
        pm = tp_mean_m.sel(month=month).values * 1000.0  # m/day -> mm/day
        ps = tp_std_m.sel(month=month).values * 1000.0
        for i, la in enumerate(lat):
            for j, lo in enumerate(lon):
                if np.isnan(tm[i, j]):
                    continue
                rows.append({
                    "h3_cell": h3_grid[i, j], "month": month,
                    "lat": float(la), "lon": float(lo),
                    "temp_mean_k": float(tm[i, j]), "temp_std_k": float(ts[i, j]),
                    "precip_mean_mm": float(pm[i, j]) if not np.isnan(pm[i, j]) else None,
                    "precip_std_mm": float(ps[i, j]) if not np.isnan(ps[i, j]) else None,
                })
        print(f"[aggregate] month {month:02d} done ({len(rows)} rows so far)")
    return pd.DataFrame(rows)


def write(df: pd.DataFrame) -> None:
    now = datetime.now(timezone.utc)
    print(f"[write] {len(df)} rows -> climatology_baseline")
    records = df.to_dict("records")
    for r in records:
        r["baseline_period"] = BASELINE_PERIOD
        r["now"] = now
    with get_session() as s:
        s.execute(text("DELETE FROM climatology_baseline"))
        batch = 50_000
        for i in range(0, len(records), batch):
            chunk = records[i:i + batch]
            s.execute(text("""
                INSERT INTO climatology_baseline
                    (h3_cell, month, lat, lon, temp_mean_k, temp_std_k,
                     precip_mean_mm, precip_std_mm, baseline_period, computed_at)
                VALUES
                    (:h3_cell, :month, :lat, :lon, :temp_mean_k, :temp_std_k,
                     :precip_mean_mm, :precip_std_mm, :baseline_period, :now)
                ON CONFLICT (h3_cell, month) DO UPDATE SET
                    temp_mean_k=EXCLUDED.temp_mean_k, temp_std_k=EXCLUDED.temp_std_k,
                    precip_mean_mm=EXCLUDED.precip_mean_mm, precip_std_mm=EXCLUDED.precip_std_mm,
                    computed_at=EXCLUDED.computed_at
            """), chunk)
            print(f"[write] {min(i+batch, len(records))}/{len(records)}")


def main():
    zip_path = fetch()
    ds_t2m, ds_tp = _extract(zip_path)
    df = aggregate(ds_t2m, ds_tp)
    write(df)
    print(f"[done] {len(df)} (h3_cell, month) rows written, baseline_period={BASELINE_PERIOD}")


if __name__ == "__main__":
    main()
