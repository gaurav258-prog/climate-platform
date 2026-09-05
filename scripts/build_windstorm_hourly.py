"""Global/CONUS EXTREME-wind climatology via the HOURLY ERA5 endpoint (fast path).

Same physically-correct metric as build_windstorm_extreme_climatology.py — per-cell ANNUAL-MAXIMUM 10 m wind
gust, reduced to mean-annual-max + Gumbel 50-yr return level — but fetched from reanalysis-era5-single-levels
HOURLY i10fg (a fast, well-cached endpoint) and reduced to the annual max LOCALLY, instead of the
derived-daily-statistics service (correct but CDS-queue-bound to ~40 min/request on an overloaded day).

Per year: one hourly request (CONUS fits in a single call), per-cell max over all 8,760 hours → annual max,
cache the .npy, discard the raw. Resumable: a year whose annual-max .npy exists is skipped.

Output: data/wind/windstorm_gust_<region>.npz (lat, lon, gust_ms = 50-yr return level, mean_annual_max).
Run:  PYTHONPATH=. .venv/bin/python scripts/build_windstorm_hourly.py conus
"""
from __future__ import annotations

import os
import sys

import numpy as np

from core.config import settings

YEARS = list(range(2009, 2024))
GRID = [0.5, 0.5]
REGIONS = {
    "conus": {"area": [50, -125, 24, -66], "anndir": "data/wind/annmax_conus_hr",
              "out": "data/wind/windstorm_gust_conus.npz"},
}
REGION = sys.argv[1] if len(sys.argv) > 1 else "conus"
ANNDIR = REGIONS[REGION]["anndir"]
OUT = REGIONS[REGION]["out"]
_AREA = REGIONS[REGION]["area"]
_HOURS = [f"{h:02d}:00" for h in range(24)]


# CDS latency is queue-dominated today, so MINIMISE request count: one full-year hourly request per year
# (proven to fit — a full CONUS year returns ~149 MB), reduced to the per-cell annual max locally.
def _year_annual_max(c, year: int) -> str:
    npy = f"{ANNDIR}/annmax_{year}.npy"
    if os.path.exists(npy):
        return npy
    raw = f"/tmp/era5_hr_{REGION}_{year}.nc"
    req = {
        "product_type": "reanalysis", "variable": ["instantaneous_10m_wind_gust"],
        "year": str(year), "month": [f"{m:02d}" for m in range(1, 13)],
        "day": [f"{d:02d}" for d in range(1, 32)], "time": _HOURS, "grid": GRID, "data_format": "netcdf",
    }
    if _AREA is not None:
        req["area"] = _AREA
    c.retrieve("reanalysis-era5-single-levels", req, raw)
    import xarray as xr
    ds = xr.open_dataset(raw)
    v = "i10fg" if "i10fg" in ds.data_vars else list(ds.data_vars)[0]
    tdim = [d for d in ds[v].dims if d not in ("latitude", "longitude")][0]
    ann = np.nanmax(ds[v].values, axis=ds[v].dims.index(tdim)).astype("float32")
    lat, lon = ds["latitude"].values, ds["longitude"].values
    ds.close(); os.remove(raw)
    np.save(npy, ann)
    if not os.path.exists(f"{ANNDIR}/_grid.npz"):
        np.savez(f"{ANNDIR}/_grid.npz", lat=lat, lon=lon)
    print(f"  {year}: annual-max gust p50={np.nanpercentile(ann,50):.1f} max={np.nanmax(ann):.1f} m/s", flush=True)
    return npy


def _gumbel_return_level(annmax: np.ndarray, T: float = 50.0) -> np.ndarray:
    beta = np.nanstd(annmax, axis=0) * np.sqrt(6.0) / np.pi
    loc = np.nanmean(annmax, axis=0) - 0.5772 * beta
    return loc - beta * np.log(-np.log(1.0 - 1.0 / T))


def main() -> int:
    os.makedirs(ANNDIR, exist_ok=True)
    import cdsapi
    c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
    print(f"[{REGION}] hourly extreme-gust climatology {YEARS[0]}-{YEARS[-1]} …", flush=True)
    paths = [_year_annual_max(c, y) for y in YEARS]
    grid = np.load(f"{ANNDIR}/_grid.npz")
    stack = np.stack([np.load(p) for p in paths])
    mean_annual_max = np.nanmean(stack, axis=0).astype("float32")
    rl50 = _gumbel_return_level(stack, 50.0).astype("float32")
    np.savez_compressed(OUT, lat=grid["lat"], lon=grid["lon"], gust_ms=rl50, mean_annual_max=mean_annual_max)
    fin = rl50[np.isfinite(rl50)]
    print(f"\nsaved {OUT}: 50-yr return-level gust m/s p50={np.percentile(fin,50):.1f} "
          f"p90={np.percentile(fin,90):.1f} max={fin.max():.1f} ({len(paths)} years)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
