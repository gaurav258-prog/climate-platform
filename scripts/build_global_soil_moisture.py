"""Build the global 1991-2020 root-zone soil-moisture climatology baseline (global build G1).

The soil-water counterpart to scripts/build_global_climatology.py. Same proven ECMWF product
(`reanalysis-era5-single-levels-monthly-means`, one global request, cached to disk), but for the two
root-zone soil-water layers instead of temp/precip:

  * volumetric_soil_water_layer_2  (7-28 cm, ~21 cm thick)
  * volumetric_soil_water_layer_3  (28-100 cm, ~72 cm thick)

We store the DEPTH-WEIGHTED root-zone mean (m3/m3) per H3 cell per calendar month, mean + std across the
30 years — exactly the antecedent water the soil_water score standardises a live reading against. This
replaces the region-tiled Iberia .nc files so soil_water scores anywhere on Earth.

Usage:  python scripts/build_global_soil_moisture.py
"""
from __future__ import annotations

import os
import time
import zipfile
from datetime import datetime, timezone

import h3
import numpy as np
import pandas as pd
import xarray as xr
from sqlalchemy import text

from core.db.session import get_session

RAW_CACHE = "data/era5_soil_moisture_baseline/era5_monthly_swvl_1991_2020.zip"
BASELINE_PERIOD = "1991-2020"
YEARS = list(range(1991, 2021))
H3_RES = 8
# ERA5-Land layer thicknesses (cm): layer 2 spans 7-28 (21 cm), layer 3 spans 28-100 (72 cm).
L2_CM, L3_CM = 21.0, 72.0


def fetch() -> str:
    if os.path.exists(RAW_CACHE):
        print(f"[fetch] using cached {RAW_CACHE}")
        return RAW_CACHE
    import cdsapi
    os.makedirs(os.path.dirname(RAW_CACHE), exist_ok=True)
    c = cdsapi.Client(quiet=True)
    t0 = time.time()
    print(f"[fetch] requesting {YEARS[0]}-{YEARS[-1]}, global, swvl2+swvl3 (no cache found)...")
    c.retrieve("reanalysis-era5-single-levels-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": ["volumetric_soil_water_layer_2", "volumetric_soil_water_layer_3"],
        "year": [str(y) for y in YEARS],
        "month": [f"{m:02d}" for m in range(1, 13)],
        "time": ["00:00"],
        "format": "netcdf",
        "area": [90, -180, -90, 180],
    }, RAW_CACHE)
    print(f"[fetch] done in {time.time()-t0:.0f}s")
    return RAW_CACHE


def _open(zip_path: str) -> xr.Dataset:
    """swvl2 + swvl3 are both instantaneous fields → one NetCDF (no accum/instant split)."""
    if zipfile.is_zipfile(zip_path):
        extract_dir = os.path.dirname(zip_path) + "/_extracted"
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            zf.extractall(extract_dir)
        # merge every extracted NetCDF (both vars may share one file, or split)
        ds = xr.merge([xr.open_dataset(extract_dir + "/" + n) for n in names if n.endswith(".nc")])
    else:
        ds = xr.open_dataset(zip_path)
    return ds


def aggregate(ds: xr.Dataset) -> pd.DataFrame:
    print("[aggregate] depth-weighting root zone (swvl2*21 + swvl3*72)/93 ...")
    root = (ds["swvl2"] * L2_CM + ds["swvl3"] * L3_CM) / (L2_CM + L3_CM)
    by_month = root.groupby("valid_time.month")
    sm_mean = by_month.mean("valid_time")
    sm_std = by_month.std("valid_time", ddof=1)

    lat = ds["latitude"].values
    lon = ds["longitude"].values
    print(f"[aggregate] grid: {len(lat)} x {len(lon)} = {len(lat)*len(lon)} cells x 12 months")
    h3_grid = np.empty((len(lat), len(lon)), dtype=object)
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            h3_grid[i, j] = h3.latlng_to_cell(float(la), float(lo), H3_RES)

    rows = []
    for month in range(1, 13):
        mm = sm_mean.sel(month=month).values
        ss = sm_std.sel(month=month).values
        for i, la in enumerate(lat):
            for j, lo in enumerate(lon):
                if np.isnan(mm[i, j]):
                    continue  # ocean / no soil
                rows.append({
                    "h3_cell": h3_grid[i, j], "month": month,
                    "lat": float(la), "lon": float(lo),
                    "sm_mean": float(mm[i, j]),
                    "sm_std": float(ss[i, j]) if not np.isnan(ss[i, j]) else None,
                })
        print(f"[aggregate] month {month:02d} done ({len(rows)} rows so far)")
    return pd.DataFrame(rows)


def write(df: pd.DataFrame) -> None:
    now = datetime.now(timezone.utc)
    print(f"[write] {len(df)} rows -> soil_moisture_baseline")
    records = df.to_dict("records")
    for r in records:
        r["baseline_period"] = BASELINE_PERIOD
        r["now"] = now
    with get_session() as s:
        s.execute(text("DELETE FROM soil_moisture_baseline"))
        batch = 50_000
        for i in range(0, len(records), batch):
            s.execute(text("""
                INSERT INTO soil_moisture_baseline
                    (h3_cell, month, lat, lon, sm_mean, sm_std, baseline_period, computed_at)
                VALUES (:h3_cell, :month, :lat, :lon, :sm_mean, :sm_std, :baseline_period, :now)
                ON CONFLICT (h3_cell, month) DO UPDATE SET
                    sm_mean=EXCLUDED.sm_mean, sm_std=EXCLUDED.sm_std, computed_at=EXCLUDED.computed_at
            """), records[i:i + batch])
            s.commit()
            print(f"[write] {min(i+batch, len(records))}/{len(records)}")


def main():
    zip_path = fetch()
    ds = _open(zip_path)
    df = aggregate(ds)
    write(df)
    print(f"[done] {len(df)} (h3_cell, month) soil-moisture baseline rows, period={BASELINE_PERIOD}")


if __name__ == "__main__":
    main()
