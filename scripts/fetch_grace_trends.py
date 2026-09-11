"""NASA GRACE / GRACE-FO terrestrial water-storage trends — the independent water-stress target.

Pulls the NASA GSFC RL06 v2.0 mascon solution (GIA-removed, ICE6G-D; half-degree gridded netCDF, open, no
Earthdata login: https://earth.gsfc.nasa.gov/geo/data/grace-mascons) and computes, once, the per-cell ordinary
least-squares linear trend of monthly liquid-water-equivalent thickness (cm/yr) over the full 2002-04 → 2026-03
record, on land cells only, sampled at 1° (every second half-degree node: the native resolution of the GSFC
mascons is 1-arc-degree equal-area blocks, so the half-degree grid is an oversampling and 1° loses nothing).
Satellite gravimetry is independent of the ERA5 root-zone soil-moisture baseline the water-stress channel reads.
Lands data/water_stress_val/grace_gsfc_trends.csv (lat, lon, trend_cm_yr, n_months, year_first, year_last).
Resumable: the 530 MB netCDF is downloaded with HTTP Range if partial; the trend CSV is skipped if present.
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_grace_trends.py [--force]
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

URL = "https://earth.gsfc.nasa.gov/sites/default/files/geo/gsfc.glb_.200204_202603_rl06v2.0_obp-ice6gd_halfdegree.nc"
NC = Path("data/water_stress_val/gsfc_rl06v2_obp_ice6gd_halfdegree.nc")
OUT = Path("data/water_stress_val/grace_gsfc_trends.csv")
STEP = 2                 # every 2nd half-degree node → 1°, the mascons' native block size
MIN_MONTHS = 150         # a cell must carry ≥150 of the 255 monthly solutions to publish a trend


def download(url: str = URL, dest: Path = NC) -> Path:
    """Resumable HTTP download (Range from the current partial length)."""
    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = int(requests.head(url, timeout=60, allow_redirects=True).headers.get("Content-Length", "0"))
    have = dest.stat().st_size if dest.exists() else 0
    if total and have >= total:
        print(f"{dest} complete ({have} bytes)")
        return dest
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, headers=headers, stream=True, timeout=600) as r:
        r.raise_for_status()
        with dest.open("ab" if have else "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    print(f"downloaded {dest} ({dest.stat().st_size} bytes)")
    return dest


def decimal_years(times) -> np.ndarray:
    """datetime64 array → decimal years (fractional, for the OLS slope in per-year units)."""
    t = np.asarray(times, dtype="datetime64[D]")
    yr = t.astype("datetime64[Y]")
    start = yr.astype("datetime64[D]")
    nxt = (yr + np.timedelta64(1, "Y")).astype("datetime64[D]")
    frac = (t - start).astype(float) / (nxt - start).astype(float)
    return yr.astype(int) + 1970 + frac


def ols_trends(series: np.ndarray, t_years: np.ndarray, min_months: int = MIN_MONTHS) -> tuple[np.ndarray, np.ndarray]:
    """Per-column OLS slope (units of series per year) of a (time, n) matrix with NaN gaps.
    Returns (slope, n_valid); slope is NaN where fewer than min_months valid samples."""
    x = np.asarray(t_years, float)
    y = np.asarray(series, float)
    valid = np.isfinite(y)
    n = valid.sum(axis=0)
    yz = np.where(valid, y, 0.0)
    sx = (valid * x[:, None]).sum(axis=0)
    sy = yz.sum(axis=0)
    sxx = (valid * x[:, None] ** 2).sum(axis=0)
    sxy = (yz * x[:, None]).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        slope = (n * sxy - sx * sy) / (n * sxx - sx ** 2)
    slope = np.where(n >= min_months, slope, np.nan)
    return slope, n


def build_trends(nc: Path = NC, out: Path = OUT, step: int = STEP) -> Path:
    import xarray as xr
    ds = xr.open_dataset(nc)
    lat = ds["lat"].values[::step]
    lon = ds["lon"].values[::step]
    land = ds["land_mask"].values[::step, ::step]
    lwe = ds["lwe_thickness"].isel(lat=slice(None, None, step), lon=slice(None, None, step)).values   # (t, lat, lon)
    units = ds["lwe_thickness"].attrs.get("units", "cm")
    t_years = decimal_years(ds["time"].values)
    ny, nx = land.shape
    slope, n = ols_trends(lwe.reshape(lwe.shape[0], -1), t_years)
    slope = slope.reshape(ny, nx)
    n = n.reshape(ny, nx)
    scale = 0.1 if units.lower().startswith("mm") else (100.0 if units.lower().startswith("m") and units.lower() != "mm" else 1.0)
    out.parent.mkdir(parents=True, exist_ok=True)
    n_rows = 0
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "trend_cm_yr", "n_months", "year_first", "year_last"])
        for i in range(ny):
            for j in range(nx):
                if land[i, j] < 0.5 or not np.isfinite(slope[i, j]):
                    continue
                lo = float(lon[j])
                lo = lo - 360.0 if lo > 180.0 else lo
                w.writerow([f"{float(lat[i]):.2f}", f"{lo:.2f}", f"{slope[i, j] * scale:.4f}", int(n[i, j]),
                            int(t_years[0]), int(t_years[-1])])
                n_rows += 1
    print(f"wrote {out}: {n_rows} land cells at {step * 0.5:.1f}°, {len(t_years)} monthly solutions "
          f"{ds['time'].values[0]!s:.10} → {ds['time'].values[-1]!s:.10}, lwe units '{units}'")
    return out


def main(argv: list[str]) -> int:
    force = "--force" in argv
    download()
    if OUT.exists() and not force:
        print(f"{OUT} present — skip (use --force to recompute)")
        return 0
    build_trends()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
