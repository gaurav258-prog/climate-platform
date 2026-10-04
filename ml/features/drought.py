"""
Drought feature extractor — SPI / SPEI from ERA5-Land monthly data.

The agriculture-critical hazard the platform was missing. Computes, per grid cell:
  SPI-n   — Standardized Precipitation Index over an n-month window (precip only)
  SPEI-n  — same on the climatic water balance D = precipitation − potential evapotranspiration
  precip_deficit_mm, temp anomaly vs the 1991–2020 normal.

v0 uses a GAUSSIAN standardization (z-score of the n-month accumulation against the
1991–2020 monthly climatology). The textbook SPI fits a gamma distribution and SPEI a
log-logistic; the z-score is the honest, transparent baseline and the gamma/LL fit is the
documented refinement. Consumes the monthly NetCDF from scripts/fetch_era5_baseline.py
(vars: tp, t2m, pev) — no dependency on the live obs store, so it also drives the backtest.
"""
from __future__ import annotations

import glob
import os
import re
from pathlib import Path

import numpy as np
import xarray as xr

WMO_BASELINE = ("1991", "2020")  # WMO standard normal


ERA5_BASELINE_DIR = Path(__file__).resolve().parents[2] / "data" / "era5_baseline"   # the repository's, whatever the cwd


def baseline_nc(region: str, kind: str = "monthly") -> str:
    """Path to a region's ERA5 baseline, preferring the WIDEST year span available.

    Baselines are named `<region>_<y0>_<y1>_<kind>.nc`. A longer series (e.g. 1961–2024 vs the
    legacy 1991–2024) carries more drought/heat events, which is what an honest out-of-sample fit
    needs — so when both exist we pick the longer one automatically, no caller change. Falls back to
    the legacy 1991–2024 name when nothing matches (keeps existing behaviour if a region has one file).
    """
    cands = glob.glob(str(ERA5_BASELINE_DIR / f"{region}_*_{kind}.nc"))
    if not cands:
        return str(ERA5_BASELINE_DIR / f"{region}_1991_2024_{kind}.nc")

    def _span(p: str) -> int:
        m = re.search(r"_(\d{4})_(\d{4})_", os.path.basename(p))
        return (int(m.group(2)) - int(m.group(1))) if m else 0

    return max(cands, key=_span)


def load_monthly(nc_path: str) -> xr.Dataset:
    """Open the ERA5-Land monthly file and derive P, PET, water-balance D (all mm/month-rate)."""
    ds = xr.open_dataset(nc_path)
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    ds = ds.rename({tname: "time"}) if tname != "time" else ds
    # ERA5-Land monthly means are daily-rate in metres; ×1000 → mm. pev is negative (a sink).
    P = (ds["tp"] * 1000.0).rename("P")
    PET = (ds["pev"].where(ds["pev"] < 0, 0) * -1000.0).rename("PET")  # to positive mm
    D = (P - PET).rename("D")
    T = (ds["t2m"] - 273.15).rename("T")  # K → °C
    return xr.Dataset({"P": P, "PET": PET, "D": D, "T": T})


def _standardize(x: xr.DataArray, scale: int, baseline=WMO_BASELINE) -> xr.DataArray:
    """z-score of the `scale`-month rolling sum against the per-calendar-month baseline normal."""
    acc = x.rolling(time=scale, min_periods=scale).sum()
    base = acc.sel(time=slice(*baseline))
    g = base.groupby("time.month")
    mean, std = g.mean("time"), g.std("time")
    m = acc["time.month"]
    z = (acc - mean.sel(month=m)) / std.sel(month=m).where(lambda s: s > 0)
    return z.rename(f"z{scale}")


def compute_indices(ds: xr.Dataset, scale: int = 3, baseline=WMO_BASELINE) -> xr.Dataset:
    """Add spi, spei, precip_deficit_mm, temp_anom (per time × lat × lon)."""
    spi = _standardize(ds["P"], scale, baseline).rename("spi")
    spei = _standardize(ds["D"], scale, baseline).rename("spei")
    # precip deficit vs the n-month normal (mm), and temperature anomaly vs monthly normal (°C)
    Pacc = ds["P"].rolling(time=scale, min_periods=scale).sum()
    pbase = Pacc.sel(time=slice(*baseline)).groupby("time.month").mean("time")
    deficit = (Pacc - pbase.sel(month=Pacc["time.month"])).rename("precip_deficit_mm")
    tbase = ds["T"].sel(time=slice(*baseline)).groupby("time.month").mean("time")
    tanom = (ds["T"] - tbase.sel(month=ds["T"]["time.month"])).rename("temp_anom_c")
    return xr.Dataset({"spi": spi, "spei": spei,
                       "precip_deficit_mm": deficit, "temp_anom_c": tanom})


def seasonal_by_year(idx: xr.Dataset, months: list[int], region_reduce=("latitude", "longitude")) -> "list[dict]":
    """
    Region-mean drought/heat per crop-year, for the given season months (the backtest input).
    Returns one dict per year with spei/spi/temp anomaly averaged over the season & region — each figure only when
    every season month has it, else None (E167): SPEI-6 for April 1991 needs Nov 1990, which the record does not
    hold, so 1991's Apr–Aug season has no SPEI; a mean of its Jun–Aug months would be a different quantity.
    """
    sub = idx.sel(time=idx["time.month"].isin(months))
    reg = sub.mean(dim=list(region_reduce), skipna=True)
    yrs = reg["time"].dt.year
    out = []
    for yr in np.unique(yrs.values):
        y = reg.sel(time=yrs == yr)
        out.append({
            "year": int(yr),
            "spei": season_mean(y["spei"].values, len(months), 2),
            "spi": season_mean(y["spi"].values, len(months), 2),
            "temp_anom_c": season_mean(y["temp_anom_c"].values, len(months), 2),
            "precip_deficit_mm": season_mean(y["precip_deficit_mm"].values, len(months), 1),
        })
    return out


def season_mean(values, n_months: int, digits: int):
    """The season's mean when all `n_months` months have a value, else None — never a mean over part of a season
    (a record's first months without their accumulation window, a season still in progress at its end). E167."""
    v = np.asarray(values, dtype=float)
    if v.size != n_months or not np.isfinite(v).all():
        return None
    return round(float(v.mean()), digits)


def to_h3_frame(idx: xr.Dataset, year: int, month: int, resolution: int = 8):
    """One month's grid → per-H3-cell drought features (for ml_features_drought / scoring)."""
    import h3
    import pandas as pd
    snap = idx.sel(time=(idx["time"].dt.year == year) & (idx["time"].dt.month == month))
    if snap.time.size == 0:
        return pd.DataFrame()
    snap = snap.isel(time=0)
    rows = []
    lats = snap["latitude"].values
    lons = snap["longitude"].values
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            spi = float(snap["spi"].values[i, j]); spei = float(snap["spei"].values[i, j])
            if np.isnan(spi) and np.isnan(spei):
                continue
            rows.append({
                "h3_cell": h3.latlng_to_cell(float(la), float(lo), resolution),
                "spi_3month": None if np.isnan(spi) else spi,
                "spei_3month": None if np.isnan(spei) else spei,
                "precip_deficit_mm": float(snap["precip_deficit_mm"].values[i, j]),
                "era5_temp_anomaly_c": float(snap["temp_anom_c"].values[i, j]),
            })
    return pd.DataFrame(rows)
