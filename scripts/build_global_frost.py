"""Build the global 1991-2020 frost baseline from the ERA5 DIURNAL night-time temperature (global build G2).

Frost is the coldest NIGHT, which a monthly-MEAN temperature baseline misses. ERA5's raw daily-minimum
field is not carried in the monthly-means product, so instead of guessing the night from the daily mean
(the proxy we rejected), this uses the ERA5 DIURNAL CYCLE — `monthly_averaged_reanalysis_by_hour_of_day`
for 2m temperature, one global request — and takes the COLDEST HOUR of the average day per cell per month
as the night-time minimum (genuine night temperature, not the daily mean). Per H3 cell per month:
  * tmin_mean_c     — coldest-hour (night) mean across the 30 years
  * tmin_std_c      — its inter-annual std
  * coldest_night_c — climatological coldest-night estimate = tmin_mean_c − 1.5·tmin_std_c
                      (typical cold-extreme night; full daily extreme-value is the documented refinement).

Replaces the Brazil-only region files so frost scores anywhere on Earth.

Usage:  python scripts/build_global_frost.py
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

RAW_CACHE = "data/era5_frost_baseline/era5_monthly_mn2t_1991_2020.zip"
BASELINE_PERIOD = "1991-2020"
YEARS = list(range(1991, 2021))
H3_RES = 8
COLD_EXTREME_SIGMA = 1.5   # coldest-night estimate = mean daily-min − this many inter-annual std


def fetch() -> list[str]:
    """The 24-hour diurnal cycle is too many fields for one CDS request (24h × 120mo = 2880 → 403).
    Split PER YEAR (24h × 12mo = 288 fields, safely under the limit). Each year is cached separately and
    reused, so a re-run resumes where it left off. Coarser 0.5° grid keeps each request light — frost is a
    broad-scale climate feature, not a sub-km one."""
    import cdsapi
    os.makedirs(os.path.dirname(RAW_CACHE), exist_ok=True)
    c = cdsapi.Client(quiet=True)
    paths = []
    for y in YEARS:
        path = RAW_CACHE.replace(".zip", f"_{y}.zip")
        if os.path.exists(path):
            paths.append(path)
            continue
        t0 = time.time()
        print(f"[fetch] year {y}: global 0.5deg 2m-temp diurnal cycle (288 fields)...")
        c.retrieve("reanalysis-era5-single-levels-monthly-means", {
            "product_type": ["monthly_averaged_reanalysis_by_hour_of_day"],
            "variable": ["2m_temperature"],
            "year": [str(y)],
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time": [f"{h:02d}:00" for h in range(24)],
            "grid": [0.5, 0.5],
            "format": "netcdf",
            "area": [90, -180, -90, 180],
        }, path)
        print(f"[fetch] year {y} done in {time.time()-t0:.0f}s")
        paths.append(path)
    return paths


def _open(paths: list[str]) -> xr.Dataset:
    """Open + concat the per-decade files along time."""
    dsets = []
    for zip_path in paths:
        if zipfile.is_zipfile(zip_path):
            extract_dir = zip_path.replace(".zip", "_extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                zf.extractall(extract_dir)
            dsets.append(xr.merge([xr.open_dataset(extract_dir + "/" + n) for n in names if n.endswith(".nc")]))
        else:
            dsets.append(xr.open_dataset(zip_path))
    tcoord = "valid_time" if "valid_time" in dsets[0].coords else "time"
    return xr.concat(dsets, dim=tcoord)


def aggregate(ds: xr.Dataset) -> pd.DataFrame:
    var = "t2m" if "t2m" in ds else list(ds.data_vars)[0]
    print(f"[aggregate] var={var}; coldest-hour per year-month → per-month climatology ...")
    t2m = ds[var]
    tcoord = "valid_time" if "valid_time" in t2m.coords else "time"
    # coldest HOUR within each (year, month) = the night-time minimum for that month/year
    ym = (t2m[tcoord].dt.year * 100 + t2m[tcoord].dt.month).rename("ym")
    coldest = t2m.assign_coords(ym=ym).groupby("ym").min(tcoord)
    # climatology across years, per calendar month
    coldest = coldest.assign_coords(month=(coldest["ym"] % 100))
    by_month = coldest.groupby("month")
    mean_k = by_month.mean("ym")
    std_k = by_month.std("ym", ddof=1)

    lat = ds["latitude"].values
    lon = ds["longitude"].values
    print(f"[aggregate] grid: {len(lat)} x {len(lon)} = {len(lat)*len(lon)} cells x 12 months")
    h3_grid = np.empty((len(lat), len(lon)), dtype=object)
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            h3_grid[i, j] = h3.latlng_to_cell(float(la), float(lo), H3_RES)

    rows = []
    for month in range(1, 13):
        mk = mean_k.sel(month=month).values - 273.15   # K → °C
        sk = std_k.sel(month=month).values
        for i, la in enumerate(lat):
            for j, lo in enumerate(lon):
                if np.isnan(mk[i, j]):
                    continue
                std_c = float(sk[i, j]) if not np.isnan(sk[i, j]) else 0.0
                rows.append({
                    "h3_cell": h3_grid[i, j], "month": month,
                    "lat": float(la), "lon": float(lo),
                    "tmin_mean_c": float(mk[i, j]), "tmin_std_c": std_c,
                    "coldest_night_c": float(mk[i, j]) - COLD_EXTREME_SIGMA * std_c,
                })
        print(f"[aggregate] month {month:02d} done ({len(rows)} rows so far)")
    return pd.DataFrame(rows)


def write(df: pd.DataFrame) -> None:
    now = datetime.now(timezone.utc)
    print(f"[write] {len(df)} rows -> frost_baseline")
    records = df.to_dict("records")
    for r in records:
        r["baseline_period"] = BASELINE_PERIOD
        r["now"] = now
    with get_session() as s:
        s.execute(text("DELETE FROM frost_baseline"))
        batch = 50_000
        for i in range(0, len(records), batch):
            s.execute(text("""
                INSERT INTO frost_baseline
                    (h3_cell, month, lat, lon, tmin_mean_c, tmin_std_c, coldest_night_c,
                     baseline_period, computed_at)
                VALUES (:h3_cell, :month, :lat, :lon, :tmin_mean_c, :tmin_std_c, :coldest_night_c,
                        :baseline_period, :now)
                ON CONFLICT (h3_cell, month) DO UPDATE SET
                    tmin_mean_c=EXCLUDED.tmin_mean_c, tmin_std_c=EXCLUDED.tmin_std_c,
                    coldest_night_c=EXCLUDED.coldest_night_c, computed_at=EXCLUDED.computed_at
            """), records[i:i + batch])
            s.commit()
            print(f"[write] {min(i+batch, len(records))}/{len(records)}")


def main():
    ds = _open(fetch())
    write(aggregate(ds))
    print(f"[done] frost_baseline built, period={BASELINE_PERIOD}")


if __name__ == "__main__":
    main()
