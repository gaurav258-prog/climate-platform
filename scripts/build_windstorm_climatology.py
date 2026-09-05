"""Global extreme-wind (windstorm) climatology — the authoritative field behind the EU-Taxonomy
'Storm (blizzard, dust, sand)' hazard, distinct from the tropical-cyclone channel.

EU Taxonomy Appendix A lists 'Storm (blizzard/dust/sand)' as a wind hazard SEPARATE from
'Cyclone/hurricane/typhoon'. Our tropical-cyclone channel (IBTrACS Rankine vortex) does not represent
extratropical windstorms — the DOMINANT wind peril for European (EBA) banks (Kyrill, Lothar, Xynthia) — nor
blizzards/dust/sandstorms. This builds the missing field: the climatological peak 10 m wind gust from ERA5
(instantaneous_10m_wind_gust, i10fg), the authoritative reanalysis gust variable, over 1991-2020. Per cell we
take the mean seasonal cycle (average each calendar month across years) and keep its MAX month — the typical
stormiest-month gust — an authoritative RELATIVE windstorm-exposure field (not a return-period return level).

Output: data/wind/windstorm_gust_climatology.npz (lat, lon, gust_ms) — read by ml/scoring/windstorm_point.py.
Run (needs a Copernicus CDS key; a few minutes):  PYTHONPATH=. .venv/bin/python scripts/build_windstorm_climatology.py
"""
from __future__ import annotations

import numpy as np
import xarray as xr

from core.config import settings

YEARS = [str(y) for y in range(1991, 2021)]
MONTHS = [f"{m:02d}" for m in range(1, 13)]
GRID = [0.5, 0.5]
RAW = "/tmp/era5_gust_climatology.nc"
OUT = "data/wind/windstorm_gust_climatology.npz"


def main() -> int:
    import cdsapi
    c = cdsapi.Client(url=settings.CDSAPI_URL, key=settings.CDSAPI_KEY, quiet=False)
    print(f"fetching ERA5 i10fg monthly means {YEARS[0]}-{YEARS[-1]} at {GRID[0]}° …", flush=True)
    c.retrieve("reanalysis-era5-single-levels-monthly-means", {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": ["instantaneous_10m_wind_gust"],
        "year": YEARS, "month": MONTHS, "time": ["00:00"],
        "grid": GRID, "data_format": "netcdf",
    }, RAW)

    ds = xr.open_dataset(RAW)
    v = "i10fg" if "i10fg" in ds.data_vars else list(ds.data_vars)[0]
    da = ds[v]
    tdim = [d for d in da.dims if d not in ("latitude", "longitude")][0]
    # mean seasonal cycle: average each calendar month across years, then the stormiest month per cell
    times = ds[tdim].values
    months = np.array([int(str(t)[5:7]) for t in np.datetime_as_string(times)])
    arr = da.values  # (time, lat, lon)
    clim = np.stack([np.nanmean(arr[months == m], axis=0) for m in range(1, 13)])  # (12, lat, lon)
    gust = np.nanmax(clim, axis=0)  # stormiest-month mean gust per cell (m/s)

    import os
    os.makedirs("data/wind", exist_ok=True)
    np.savez_compressed(OUT, lat=ds["latitude"].values, lon=ds["longitude"].values, gust_ms=gust.astype("float32"))
    finite = gust[np.isfinite(gust)]
    print(f"saved {OUT}: grid {gust.shape}, gust m/s p50={np.percentile(finite,50):.1f} "
          f"p90={np.percentile(finite,90):.1f} max={finite.max():.1f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
