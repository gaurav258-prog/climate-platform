"""Build the global severe-convective-potential climatology (EU-Taxonomy wind hazard: tornado / large hail).

The physically grounded, global representation of the tornado/hail/damaging-wind peril is the convective-storm
ENVIRONMENT — the co-presence of instability (CAPE) and deep-layer (0–6 km) wind shear, i.e. the WMAXSHEAR
proxy of Taszarek et al. (2021). We build it from ERA5 monthly means via the Copernicus CDS:

  CAPE       reanalysis-era5-single-levels-monthly-means  (convective_available_potential_energy)
  winds      reanalysis-era5-pressure-levels-monthly-means (u/v at 500 hPa ≈ 5.5 km and 925 hPa near-surface)

Method: average each calendar month across YEARS → 12 climatological fields; per grid cell pick the PEAK-CAPE
month (the convective season) and combine that month's CAPE with that month's deep-layer bulk shear as
  potential = sqrt(2·CAPE) · shear            [Taszarek WMAXSHEAR form]
then normalise to 0–100 by the global 99th percentile. Written to data/convective/convective_potential.npz
(lat, lon, potential) — read by ml/scoring/severe_convective_point.py. Monthly means (not hourly) keep the pull
small; it is a disclosed screening climatology of the ENVIRONMENT, not a tornado-frequency figure.

Run (needs ~/.cdsapirc):  .venv/bin/python -m scripts.build_convective_potential
"""
from __future__ import annotations

import os

import numpy as np
import xarray as xr

OUT = "data/convective/convective_potential.npz"
CAPE_NC = "data/convective/era5_cape_monthly.nc"
WIND_NC = "data/convective/era5_wind_monthly.nc"
YEARS = [str(y) for y in range(2019, 2024)]          # 5-year climatology
MONTHS = [f"{m:02d}" for m in range(1, 13)]


def _download() -> None:
    import cdsapi
    c = cdsapi.Client()
    if not os.path.exists(CAPE_NC):
        print("downloading ERA5 monthly-mean CAPE …", flush=True)
        c.retrieve("reanalysis-era5-single-levels-monthly-means", {
            "product_type": "monthly_averaged_reanalysis",
            "variable": "convective_available_potential_energy",
            "year": YEARS, "month": MONTHS, "time": "00:00", "data_format": "netcdf",
        }, CAPE_NC)
    if not os.path.exists(WIND_NC):
        print("downloading ERA5 monthly-mean winds (500/925 hPa) …", flush=True)
        c.retrieve("reanalysis-era5-pressure-levels-monthly-means", {
            "product_type": "monthly_averaged_reanalysis",
            "variable": ["u_component_of_wind", "v_component_of_wind"],
            "pressure_level": ["500", "925"], "year": YEARS, "month": MONTHS,
            "time": "00:00", "data_format": "netcdf",
        }, WIND_NC)


def _month_clim(da: xr.DataArray) -> xr.DataArray:
    """Average across years → one field per calendar month (dim 'month')."""
    tname = "valid_time" if "valid_time" in da.dims else ("time" if "time" in da.dims else None)
    return da.groupby(f"{tname}.month").mean(tname) if tname else da


def main() -> int:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        print(f"{OUT} already present — nothing to do."); return 0
    _download()

    cape = _month_clim(xr.open_dataset(CAPE_NC)["cape"])                 # (month, lat, lon)
    wds = xr.open_dataset(WIND_NC)
    uname = "u" if "u" in wds else [v for v in wds.data_vars if v.startswith("u")][0]
    vname = "v" if "v" in wds else [v for v in wds.data_vars if v.startswith("v")][0]
    lev = "pressure_level" if "pressure_level" in wds.dims else ("level" if "level" in wds.dims else "plev")
    u = _month_clim(wds[uname]); v = _month_clim(wds[vname])
    u5, u9 = u.sel({lev: 500}), u.sel({lev: 925})
    v5, v9 = v.sel({lev: 500}), v.sel({lev: 925})
    shear = np.hypot(u5 - u9, v5 - v9)                                  # (month, lat, lon) deep-layer bulk shear

    # per cell: the peak-CAPE month, and that month's CAPE + shear
    cape_v = cape.values                                               # (12, nlat, nlon)
    shear_v = shear.transpose("month", *cape.dims[1:]).values
    peak = np.nanargmax(np.nan_to_num(cape_v, nan=-1.0), axis=0)
    iy, ix = np.indices(peak.shape)
    cape_peak = cape_v[peak, iy, ix]
    shear_peak = shear_v[peak, iy, ix]

    potential = np.sqrt(2.0 * np.clip(cape_peak, 0, None)) * np.clip(shear_peak, 0, None)
    p99 = np.nanpercentile(potential, 99)
    score = np.clip(100.0 * potential / (p99 if p99 > 0 else 1.0), 0, 100).astype("float32")

    lat = cape[cape.dims[1]].values.astype("float32")
    lon = cape[cape.dims[2]].values.astype("float32")
    lon = np.where(lon > 180, lon - 360, lon)
    order = np.argsort(lon)
    np.savez_compressed(OUT, lat=lat, lon=lon[order], potential=score[:, order])
    print(f"wrote {OUT}: grid {score.shape}, P99 potential {p99:.0f}, "
          f"score mean {np.nanmean(score):.1f} max {np.nanmax(score):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
