"""Global EXTREME-wind (windstorm) climatology — the physically-correct field for the EU 'Storm' hazard.

Supersedes the monthly-MEAN gust field (build_windstorm_climatology.py), which measured persistent breeziness,
not episodic windstorm severity, and FAILED an independent NOAA backtest (AUC 0.45, ρ −0.21 — it ranked
calm-but-breezy Florida above Denver's high-wind Front Range). Windstorm hazard is an EXTREME: here we build
the per-cell ANNUAL-MAXIMUM daily 10 m wind gust and reduce it to (a) the mean annual maximum and (b) a Gumbel
50-year return level — the standard extreme-wind design statistics.

Source: ERA5 daily-maximum instantaneous_10m_wind_gust (i10fg), 2004-2023, 0.5°, via the CDS
derived-era5-single-levels-daily-statistics dataset. Processed YEAR BY YEAR (fetch → per-cell annual max →
discard the raw daily file), so disk/memory stay bounded. Resumable: a year whose annual-max .npy already
exists is skipped.

Output: data/wind/windstorm_gust_climatology.npz (lat, lon, gust_ms = 50-yr return level, mean_annual_max).
Run (Copernicus CDS key; multi-hour):  PYTHONPATH=. .venv/bin/python scripts/build_windstorm_extreme_climatology.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

from core.config import settings

YEARS = list(range(2009, 2024))   # 15-year climatology for annual-max / Gumbel return levels
GRID = [0.5, 0.5]
# Region: "conus" (cheap, for validating the corrected metric) or "global" (the product field). A full global
# year exceeds the CDS per-request cost limit, so global is fetched in latitude BANDS; CONUS fits per-year.
REGIONS = {
    "conus": {"area": [50, -125, 24, -66], "anndir": "data/wind/annmax_conus",
              "out": "data/wind/windstorm_gust_conus.npz", "bands": None},
    "global": {"area": None, "anndir": "data/wind/annmax", "out": "data/wind/windstorm_gust_climatology.npz",
               "bands": [[90, -180, 30, 180], [30, -180, -30, 180], [-30, -180, -90, 180]]},
}
REGION = sys.argv[1] if len(sys.argv) > 1 else "conus"
ANNDIR = REGIONS[REGION]["anndir"]
OUT = REGIONS[REGION]["out"]
_AREA = REGIONS[REGION]["area"]


# CDS daily-statistics cost is driven by the number of DAYS (each day = 24 hourly global reads), not the output
# area — a full year is rejected, a quarter fits. So fetch by quarter and take the per-cell max across quarters.
_QUARTERS = [["01", "02", "03"], ["04", "05", "06"], ["07", "08", "09"], ["10", "11", "12"]]


def _fetch_quarter_max(c, year: int, qi: int, months: list[str]) -> str:
    npy = f"{ANNDIR}/qmax_{year}_q{qi}.npy"
    if os.path.exists(npy):
        return npy
    raw = f"/tmp/era5_dmax_{year}_q{qi}.nc"
    req = {
        "product_type": "reanalysis", "variable": ["instantaneous_10m_wind_gust"],
        "year": str(year), "month": months, "day": [f"{d:02d}" for d in range(1, 32)],
        "daily_statistic": "daily_maximum", "time_zone": "utc+00:00", "frequency": "1_hourly", "grid": GRID,
    }
    if _AREA is not None:
        req["area"] = _AREA
    c.retrieve("derived-era5-single-levels-daily-statistics", req, raw)
    import xarray as xr
    ds = xr.open_dataset(raw)
    v = "i10fg" if "i10fg" in ds.data_vars else list(ds.data_vars)[0]
    tdim = [d for d in ds[v].dims if d not in ("latitude", "longitude")][0]
    qmax = np.nanmax(ds[v].values, axis=ds[v].dims.index(tdim)).astype("float32")
    lat, lon = ds["latitude"].values, ds["longitude"].values
    ds.close(); os.remove(raw)
    np.save(npy, qmax)
    if not os.path.exists(f"{ANNDIR}/_grid.npz"):
        np.savez(f"{ANNDIR}/_grid.npz", lat=lat, lon=lon)
    return npy


def _fetch_year_annual_max(c, year: int) -> str:
    """Annual max = per-cell max over the 4 quarterly daily-max fields. Cached, resumable at quarter granularity."""
    npy = f"{ANNDIR}/annmax_{year}.npy"
    if os.path.exists(npy):
        return npy
    qpaths = [_fetch_quarter_max(c, year, qi, months) for qi, months in enumerate(_QUARTERS)]
    ann = np.nanmax(np.stack([np.load(p) for p in qpaths]), axis=0).astype("float32")
    np.save(npy, ann)
    for p in qpaths:
        os.remove(p)
    print(f"  {year}: annual-max gust p50={np.nanpercentile(ann,50):.1f} max={np.nanmax(ann):.1f} m/s", flush=True)
    return npy


def _gumbel_return_level(annmax: np.ndarray, T: float = 50.0) -> np.ndarray:
    """Per-cell Gumbel (method-of-moments) T-year return level from the stack of annual maxima (n_years, ny, nx)."""
    mu_hat = np.nanmean(annmax, axis=0)
    sd = np.nanstd(annmax, axis=0)
    beta = sd * np.sqrt(6.0) / np.pi                    # Gumbel scale
    loc = mu_hat - 0.5772 * beta                        # Gumbel location
    return loc - beta * np.log(-np.log(1.0 - 1.0 / T))  # return level


def main() -> int:
    os.makedirs(ANNDIR, exist_ok=True)
    import cdsapi
    c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
    print(f"building extreme-gust climatology {YEARS[0]}-{YEARS[-1]} (annual-max daily gust, 0.5°) …", flush=True)
    paths = [_fetch_year_annual_max(c, y) for y in YEARS]

    grid = np.load(f"{ANNDIR}/_grid.npz")
    stack = np.stack([np.load(p) for p in paths])       # (n_years, ny, nx)
    mean_annual_max = np.nanmean(stack, axis=0).astype("float32")
    rl50 = _gumbel_return_level(stack, 50.0).astype("float32")
    np.savez_compressed(OUT, lat=grid["lat"], lon=grid["lon"], gust_ms=rl50, mean_annual_max=mean_annual_max)
    fin = rl50[np.isfinite(rl50)]
    print(f"\nsaved {OUT}: 50-yr return-level gust m/s p50={np.percentile(fin,50):.1f} "
          f"p90={np.percentile(fin,90):.1f} max={fin.max():.1f} (over {len(paths)} years)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
