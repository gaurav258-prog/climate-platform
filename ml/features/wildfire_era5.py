"""
Shared ERA5-Land wildfire feature computation — the SAME definition used by the
multi-event trainer (scripts/build_multievent_wildfire.py) and on-demand point
scoring, so they can never diverge (same convention as ml/features/flood_era5.py).

Five features, all derivable from ONE ERA5-Land request (no separate satellite
product needed — confirmed via the training script this mirrors):
  gfs_wind_speed_ms         — sqrt(u10^2 + v10^2), peak-day
  gfs_relative_humidity_pct — Magnus formula from 2m temp + dewpoint, peak-day
  days_since_last_rain      — consecutive dry days (<1mm) walking back from peak
  fuel_load_lai             — leaf-area-index (high+low veg) = burnable vegetation
  soil_moisture             — volumetric soil water layer 1 (dry = fire-prone)
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from datetime import date, timedelta

import h3
import numpy as np
import pandas as pd
import xarray as xr

FEATURE_COLS = ["gfs_wind_speed_ms", "gfs_relative_humidity_pct", "days_since_last_rain",
                "fuel_load_lai", "soil_moisture"]
VARS = ["10m_u_component_of_wind", "10m_v_component_of_wind",
        "2m_temperature", "2m_dewpoint_temperature", "total_precipitation",
        "leaf_area_index_high_vegetation", "leaf_area_index_low_vegetation",
        "volumetric_soil_water_layer_1"]
H3_RES = 8
WINDOW_DAYS = 15  # days before peak, for days-since-rain (matches the trainer)
DRY_THRESHOLD_MM = 1.0


def fetch_era5(area: list[float], peak: date, window: int = WINDOW_DAYS) -> xr.Dataset:
    """One CDS request for the `window`-day run-up to `peak` over `area` [N,W,S,E]."""
    import cdsapi
    days = [peak - timedelta(days=k) for k in range(window)]
    c = cdsapi.Client(quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False); tmp.close()
    c.retrieve("reanalysis-era5-land", {
        "variable": VARS,
        "year": sorted({str(d.year) for d in days}),
        "month": sorted({f"{d.month:02d}" for d in days}),
        "day": sorted({f"{d.day:02d}" for d in days}),
        "time": ["12:00"],  # midday: hottest/driest, peak fire weather
        "area": area, "format": "netcdf",
    }, tmp.name)
    path = tmp.name
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            nc = [n for n in zf.namelist() if n.endswith(".nc")][0]
            out = path + "_d.nc"
            with zf.open(nc) as s, open(out, "wb") as d:
                shutil.copyfileobj(s, d)
        os.unlink(path); path = out
    return xr.open_dataset(path)


def _rh(t_k, td_k):
    t, td = t_k - 273.15, td_k - 273.15
    es = np.exp(17.625 * t / (243.04 + t))
    e = np.exp(17.625 * td / (243.04 + td))
    return np.clip(100.0 * e / es, 0, 100)


def compute_features(ds: xr.Dataset) -> pd.DataFrame:
    """ERA5-Land dataset -> one row per H3 cell with the 5 wildfire features."""
    tvar = "valid_time" if "valid_time" in ds else "time"
    lat = ds["latitude"].values
    lon = ds["longitude"].values
    u, v = ds["u10"], ds["v10"]
    t2, d2 = ds["t2m"], ds["d2m"]
    tp = ds["tp"]

    wind = np.sqrt(u.isel({tvar: -1}) ** 2 + v.isel({tvar: -1}) ** 2).values
    rh = _rh(t2.isel({tvar: -1}).values, d2.isel({tvar: -1}).values)
    lai = ds["lai_hv"].isel({tvar: -1}).values + ds["lai_lv"].isel({tvar: -1}).values
    sm = ds["swvl1"].isel({tvar: -1}).values

    tp_mm = (tp * 1000.0).values  # (time, lat, lon)
    nt = tp_mm.shape[0]
    dslr = np.zeros_like(wind)
    for i in range(wind.shape[0]):
        for j in range(wind.shape[1]):
            cnt = 0
            for k in range(nt - 1, -1, -1):
                if np.isnan(tp_mm[k, i, j]) or tp_mm[k, i, j] >= DRY_THRESHOLD_MM:
                    break
                cnt += 1
            dslr[i, j] = cnt

    rows = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            if np.isnan(wind[i, j]):
                continue
            rows.append({
                "h3_cell": h3.latlng_to_cell(float(la), float(lo), H3_RES),
                "gfs_wind_speed_ms": float(wind[i, j]),
                "gfs_relative_humidity_pct": float(rh[i, j]),
                "days_since_last_rain": float(dslr[i, j]),
                "fuel_load_lai": float(lai[i, j]) if not np.isnan(lai[i, j]) else 0.0,
                "soil_moisture": float(sm[i, j]) if not np.isnan(sm[i, j]) else 0.0,
            })
    if not rows:
        return pd.DataFrame(columns=["h3_cell"] + FEATURE_COLS)
    return pd.DataFrame(rows).groupby("h3_cell", as_index=False).agg(
        gfs_wind_speed_ms=("gfs_wind_speed_ms", "max"),
        gfs_relative_humidity_pct=("gfs_relative_humidity_pct", "min"),
        days_since_last_rain=("days_since_last_rain", "max"),
        fuel_load_lai=("fuel_load_lai", "max"),
        soil_moisture=("soil_moisture", "min"))
