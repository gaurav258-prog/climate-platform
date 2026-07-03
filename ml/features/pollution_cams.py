"""
Shared CAMS pollution feature computation — mirrors flood_era5.py's shape
(fetch_* + compute_features, one definition reused by both backtest and live
on-demand scoring so they can never diverge).

**Two CAMS products, deliberately, same reasoning as this project's existing
ERA5 vs ERA5-Land distinction**: `cams-global-atmospheric-composition-forecasts`
(pure forward model, no observation assimilation after the forecast is issued)
is right for a live "what's the air like right now" lookup, but WRONG for
reconstructing a past event — a real bug caught live in this project via honest
ground-truth comparison: scoring the 2020 California wildfire smoke event via
the forecast archive returned PM2.5 ~1.5-24µg/m³ against a real station reading
of ~129µg/m³ (a near-total miss), while `cams-global-reanalysis-eac4` (EAC4 —
assimilates real observations after the fact, the CAMS equivalent of ERA5
reanalysis) returned 45-70µg/m³ for the same point/day — same order of magnitude,
correctly severe. **Rule: use `fetch_cams_reanalysis` for any date in the past
(backtests), `fetch_cams_forecast` only for scoring "today."**

**Scope decision, disclosed not hidden**: both datasets only expose PM2.5/PM10
as simple single-level surface concentrations (kg/m³). NO2/SO2/O3 exist too, but
ONLY as multi-level mixing ratios (kg/kg) requiring a pressure-level pick
(confirmed via the forecast dataset's own form.json — no single-level surface
product for them) plus density conversion using co-retrieved temperature/
pressure — real extra work for pollutants that are not the driver in either
backtest target (Delhi Nov-2024 smog and the 2020 California wildfire smoke are
both PM-dominated events, same as most real-world AQI alerts).
`ml/scoring/pollution_aqi.py` already accepts NO2/SO2/O3 as optional and simply
omits them from the max-of-sub-scores when absent — so adding them later is
additive, not a rework. Flagged as follow-on work, same "disclose the gap"
convention as frost (blocked on CDS) and MIROVA (no API).

CAMS reports PM concentrations in kg/m³; WHO AQG thresholds (ml/scoring/
pollution_aqi.py) are in µg/m³, hence the ×1e9 conversion below.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from datetime import date

import h3
import numpy as np
import pandas as pd
import xarray as xr

from core.config import settings

FEATURE_COLS = ["pm25_ugm3", "pm10_ugm3"]
VARS = ["particulate_matter_2.5um", "particulate_matter_10um"]
H3_RES = 8
KG_M3_TO_UG_M3 = 1e9


def _client():
    import cdsapi
    return cdsapi.Client(url=settings.ADSAPI_URL, key=settings.ADSAPI_KEY or settings.CDSAPI_KEY,
                          quiet=True)


def _extract_if_zip(path: str) -> str:
    if not zipfile.is_zipfile(path):
        return path
    with zipfile.ZipFile(path) as zf:
        nc = [n for n in zf.namelist() if n.endswith(".nc")][0]
        out = path + "_d.nc"
        with zf.open(nc) as s, open(out, "wb") as d:
            shutil.copyfileobj(s, d)
    os.unlink(path)
    return out


def fetch_cams_forecast(area: list[float], day: date) -> xr.Dataset:
    """Live/near-real-time PM2.5+PM10 (hour-0 forecast) — for "today" on-demand lookups only."""
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False); tmp.close()
    _client().retrieve("cams-global-atmospheric-composition-forecasts", {
        "variable": VARS,
        "date": [f"{day.isoformat()}/{day.isoformat()}"],
        "time": ["00:00"],
        "leadtime_hour": ["0"],
        "type": ["forecast"],
        "area": area,
        "format": "netcdf",
    }, tmp.name)
    return xr.open_dataset(_extract_if_zip(tmp.name))


def fetch_cams_reanalysis(area: list[float], day: date) -> xr.Dataset:
    """EAC4 reanalysis, all 4 daily times — for backtesting a PAST event (see module docstring)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False); tmp.close()
    _client().retrieve("cams-global-reanalysis-eac4", {
        "variable": VARS,
        "date": [f"{day.isoformat()}/{day.isoformat()}"],
        "time": ["00:00", "06:00", "12:00", "18:00"],
        "area": area,
        "format": "netcdf",
    }, tmp.name)
    return xr.open_dataset(_extract_if_zip(tmp.name))


def compute_features(ds: xr.Dataset) -> pd.DataFrame:
    """CAMS dataset (forecast or EAC4 reanalysis shape) -> one row per H3 cell,
    daily-mean PM2.5/PM10 in µg/m³ (mean over whatever time steps are present —
    matches OpenAQ's daily-average convention used for ground-truth comparison)."""
    lat = ds["latitude"].values
    lon = ds["longitude"].values
    time_dims = [d for d in ds["pm2p5"].dims if d not in ("latitude", "longitude")]
    pm25 = (ds["pm2p5"].mean(dim=time_dims) if time_dims else ds["pm2p5"]).values * KG_M3_TO_UG_M3
    pm10 = (ds["pm10"].mean(dim=time_dims) if time_dims else ds["pm10"]).values * KG_M3_TO_UG_M3
    pm25 = np.atleast_2d(pm25)
    pm10 = np.atleast_2d(pm10)
    rows = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            if np.isnan(pm25[i, j]):
                continue
            rows.append({
                "h3_cell": h3.latlng_to_cell(float(la), float(lo), H3_RES),
                "pm25_ugm3": float(pm25[i, j]),
                "pm10_ugm3": float(pm10[i, j]),
            })
    if not rows:
        return pd.DataFrame(columns=["h3_cell"] + FEATURE_COLS)
    return pd.DataFrame(rows).groupby("h3_cell", as_index=False).agg(
        pm25_ugm3=("pm25_ugm3", "mean"), pm10_ugm3=("pm10_ugm3", "mean"))
