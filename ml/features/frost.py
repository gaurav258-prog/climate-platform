"""
Frost feature extractor — season-minimum 2m temperature, computed from RAW HOURLY
ERA5 (not CDS's `derived-era5-single-levels-daily-statistics` product).

That derived dataset's own daily_minimum statistic is ECMWF-flagged unusable
(confirmed live 2026-07-09: "An issue with the following parameters has been
identified: minimum_2m_temperature_since_previous_post_processing ... should not
be used"). Root-cause fix: pull the standard raw hourly archive (unaffected --
it's the model's raw output, not a derived statistic) via
scripts/fetch_era5_frost_hourly.py, and compute the daily/seasonal minimum
ourselves. Same signal frost_climatology.frost_score() has always expected
(the season's coldest night); only where it's computed has changed.
"""
from __future__ import annotations

import numpy as np
import xarray as xr


def load_hourly(nc_path: str) -> xr.Dataset:
    """Open the raw hourly ERA5 2m-temperature file (K), convert to degC."""
    ds = xr.open_dataset(nc_path)
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    ds = ds.rename({tname: "time"}) if tname != "time" else ds
    T = (ds["t2m"] - 273.15).rename("T")
    return xr.Dataset({"T": T})


def load_hourly_years(year_dir: str, region_key: str) -> xr.Dataset:
    """Open every per-year file scripts/fetch_era5_frost_hourly.py wrote (one CDS
    request per year, since a multi-decade request exceeds CDS's cost limit) and
    concatenate along time into a single dataset. Plain open+concat, not
    open_mfdataset -- these files are small (~15MB/year for one region) and
    open_mfdataset's default lazy chunking requires dask, which isn't a
    dependency here."""
    import glob
    paths = sorted(glob.glob(f"{year_dir}/{region_key}_*.nc"))
    if not paths:
        raise FileNotFoundError(f"no per-year frost files found under {year_dir} for {region_key}")
    parts = []
    for p in paths:
        d = xr.open_dataset(p)
        tname = "valid_time" if "valid_time" in d.coords else "time"
        d = d.rename({tname: "time"}) if tname != "time" else d
        parts.append(d)
    ds = xr.concat(parts, dim="time") if len(parts) > 1 else parts[0]
    T = (ds["t2m"] - 273.15).rename("T")
    return xr.Dataset({"T": T})


def daily_min(ds: xr.Dataset) -> xr.DataArray:
    """Hourly -> daily minimum 2m temperature, per grid cell. Computed locally --
    this IS the statistic CDS's own daily-statistics endpoint currently can't be
    trusted to deliver.

    .resample("1D") builds a REGULAR daily grid spanning the full min-to-max
    timestamp range in `ds` -- when years are fetched non-contiguously (one CDS
    request per year, see fetch_era5_frost_hourly.py), any gap years with no
    hourly data get resampled into all-NaN days rather than being absent. Drop
    those (a day with SOME missing grid cells is real and kept; a day with
    NO data at all is a gap artifact, not a data point)."""
    daily = ds["T"].resample(time="1D").min().rename("Tmin")
    return daily.dropna(dim="time", how="all")


def seasonal_by_year(ds: xr.Dataset, months: list[int], region_reduce=("latitude", "longitude")) -> "list[dict]":
    """Region-mean season-minimum Tmin per crop-year (the backtest input) --
    mirrors ml/features/drought.py's seasonal_by_year."""
    tmin = daily_min(ds)
    sub = tmin.sel(time=tmin["time.month"].isin(months))
    reg = sub.min(dim=list(region_reduce), skipna=True)  # coldest cell in the region, per day
    yrs = reg["time"].dt.year
    out = []
    for yr in np.unique(yrs.values):
        y = reg.sel(time=yrs == yr)
        out.append({"year": int(yr), "season_min_tmin_c": round(float(y.min()), 2)})
    return out


def to_h3_frame(ds: xr.Dataset, year: int, months: list[int], resolution: int = 8):
    """One crop-year's grid -> per-H3-cell season-minimum-Tmin (frost_score's input)."""
    import h3
    import pandas as pd
    tmin = daily_min(ds)
    sub = tmin.sel(time=(tmin["time.year"] == year) & tmin["time.month"].isin(months))
    if sub.time.size == 0:
        return pd.DataFrame()
    smin = sub.min(dim="time", skipna=True)
    rows = []
    lats, lons = smin["latitude"].values, smin["longitude"].values
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            v = float(smin.values[i, j])
            if np.isnan(v):
                continue
            rows.append({"h3_cell": h3.latlng_to_cell(float(la), float(lo), resolution),
                         "season_min_tmin_c": v})
    return pd.DataFrame(rows)
