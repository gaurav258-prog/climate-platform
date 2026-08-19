"""
Shared ERA5 flood feature computation — the SINGLE definition used by both the
multi-event trainer and live scoring, so they can never diverge.

The flood model uses three features per H3 cell:
  precipitation_7d_mm     — 7-day total precip (ERA5-Land total_precipitation,
                            read at 23:00 = the daily accumulation, summed over
                            the window; m→mm)
  soil_saturation_index   — volumetric soil water layer 1 on the peak day
  glofas_discharge_m3s    — ERA5-Land runoff (daily accumulation) on the peak day

ERA5-Land accumulates from 00 UTC, so the 23:00 value is the day's total. Reading
12:00 (as an earlier version did) captured only the morning half and missed
afternoon/evening convective rain — which made the model blind to flash floods.
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

FEATURE_COLS = ["precipitation_7d_mm", "soil_saturation_index", "glofas_discharge_m3s"]
VARS = ["total_precipitation", "volumetric_soil_water_layer_1", "runoff"]
H3_RES = 8
WINDOW_DAYS = 8


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
        "time": ["23:00"],
        "area": area,
        "format": "netcdf",
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


def compute_features(ds: xr.Dataset, flood_bbox: list[float] | None = None) -> pd.DataFrame:
    """ERA5 dataset → one row per H3 cell with the 3 features (+ label y if bbox given)."""
    tvar = "valid_time" if "valid_time" in ds else "time"
    lat = ds["latitude"].values; lon = ds["longitude"].values
    tp = ds["tp"]; sw = ds["swvl1"]; ro = ds["ro"] if "ro" in ds else ds.get("runoff")
    tp_sum = (tp.sum(dim=tvar) * 1000.0).values
    sw_last = sw.isel({tvar: -1}).values
    ro_last = ro.isel({tvar: -1}).values
    rows = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            if np.isnan(tp_sum[i, j]):
                continue
            row = {
                "h3_cell": h3.latlng_to_cell(float(la), float(lo), H3_RES),
                "precipitation_7d_mm": float(tp_sum[i, j]),
                "soil_saturation_index": float(sw_last[i, j]),
                "glofas_discharge_m3s": float(ro_last[i, j]),
            }
            if flood_bbox is not None:
                row["y"] = int(flood_bbox[2] <= la <= flood_bbox[0]
                               and flood_bbox[1] <= lo <= flood_bbox[3])
            rows.append(row)
    agg = {"precipitation_7d_mm": ("precipitation_7d_mm", "max"),
           "soil_saturation_index": ("soil_saturation_index", "mean"),
           "glofas_discharge_m3s": ("glofas_discharge_m3s", "max")}
    if flood_bbox is not None:
        agg["y"] = ("y", "max")
    return pd.DataFrame(rows).groupby("h3_cell", as_index=False).agg(**agg)
