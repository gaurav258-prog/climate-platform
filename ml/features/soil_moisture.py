"""Root-zone SOIL MOISTURE anomaly — the water-availability driver, an upgrade on SPEI.

SPEI measures what the sky delivered (rainfall − evapotranspiration). This measures what is
actually in the root zone: ERA5-Land volumetric soil water, layers 2 (7–28 cm) and 3 (28–100 cm),
depth-weighted into one root-zone value, then standardised the SAME way SPEI is — a z-score
against the 1991–2020 per-calendar-month normal — so it is directly comparable and drops into the
same driver search / fit. Higher z = wetter root zone = better crop (POSITIVE sign vs yield, like
SPEI).

It integrates rainfall + antecedent storage + snowmelt, so it should track crop water stress
better than a precipitation-only index — the test is empirical (does it beat SPEI on r²?), never
assumed. It still does not see reservoir irrigation; that is a separate basin-storage signal.
"""
from __future__ import annotations

import numpy as np
import xarray as xr

WMO_BASELINE = ("1991-01-01", "2020-12-31")
# ERA5-Land layer thicknesses (cm): layer 2 spans 7–28 (21 cm), layer 3 spans 28–100 (72 cm).
_L2, _L3 = 21.0, 72.0


def load_root_zone(nc_path: str) -> xr.DataArray:
    """Open the soil-moisture file and return one depth-weighted root-zone volumetric water
    series (m³/m³) over time × lat × lon."""
    ds = xr.open_dataset(nc_path)
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    ds = ds.rename({tname: "time"}) if tname != "time" else ds
    # short names swvl2/swvl3; fall back to the long names if a build used them.
    v2 = ds["swvl2"] if "swvl2" in ds else ds["volumetric_soil_water_layer_2"]
    v3 = ds["swvl3"] if "swvl3" in ds else ds["volumetric_soil_water_layer_3"]
    return ((v2 * _L2 + v3 * _L3) / (_L2 + _L3)).rename("sm")


def anomaly(sm: xr.DataArray, baseline=WMO_BASELINE) -> xr.DataArray:
    """z-score of root-zone soil moisture vs the per-calendar-month baseline normal."""
    base = sm.sel(time=slice(*baseline))
    g = base.groupby("time.month")
    mean, std = g.mean("time"), g.std("time")
    m = sm["time.month"]
    return ((sm - mean.sel(month=m)) / std.sel(month=m).where(lambda s: s > 0)).rename("sm_z")


def seasonal_by_year(sm_z: xr.DataArray, months: list[int],
                     region_reduce=("latitude", "longitude")) -> "list[dict]":
    """Region-mean root-zone soil-moisture anomaly per year over the season window — same shape
    as ml.features.drought.seasonal_by_year, so the driver search and fit are unchanged."""
    sub = sm_z.sel(time=sm_z["time.month"].isin(months))
    reg = sub.mean(dim=[d for d in region_reduce if d in sub.dims], skipna=True)
    yrs = reg["time"].dt.year
    out = []
    for yr in np.unique(yrs.values):
        y = reg.sel(time=yrs == yr)
        out.append({"year": int(yr), "sm_z": round(float(y.mean()), 3)})
    return out
