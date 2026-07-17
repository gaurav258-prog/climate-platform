"""Acute heat metrics from HOURLY temperature — the events monthly means cannot see.

WHY THIS EXISTS. Monthly means dilute the events that actually kill crops. Spain's May-2022
heatwave — two weeks above 40C straight through olive flowering — appears in monthly data as
a bland +3.05C anomaly, and the olive driver search found no index that explains the -30%
crop anomaly. Same reason coffee's July-2021 frost is invisible in monthly means. Cocoa works
on monthly data only because the harmattan is a SUSTAINED season-long signal, not a spike.

So: our data resolution decides which crops are backtestable at all. Sustained-stress crops
work on monthly; acute-event crops (olive flowering heat, coffee frost) need daily extremes
derived from the raw hourly archive.

WHAT THIS COMPUTES, per year, over a region and a season window:
  hot_days      — days with Tmax >= threshold (the classic exposure count)
  extreme_days  — days with Tmax >= threshold + 5C
  max_spell     — longest CONSECUTIVE run of hot days. This is the one that matters
                  biologically: olive flowers abort under sustained heat, and 10 days in a
                  row is not the same event as 10 hot days scattered across a month.
  hottest_day   — the season's peak Tmax
  degree_days   — sum of (Tmax - threshold) over hot days: intensity x duration in one number

Thresholds are per crop and cited by the caller — 35C is the widely used olive
flowering-abortion threshold. We take the region MEAN of daily Tmax across cells first, so a
single hot pixel cannot manufacture a heatwave; a real heatwave is synoptic and covers the
belt.
"""
from __future__ import annotations

import glob
from typing import Optional

import numpy as np
import xarray as xr


def _open_one(path: str) -> xr.Dataset:
    ds = xr.open_dataset(path)
    # CDS switched the hourly time coordinate to `valid_time`; older local files still say
    # `time`. Normalise here so everything downstream can assume one name.
    tname = "valid_time" if "valid_time" in ds.coords else "time"
    if tname != "time":
        ds = ds.rename({tname: "time"})
    return ds


def load_hourly(pattern: str) -> xr.Dataset:
    """Open the per-year hourly files (fetch_era5_frost_hourly.py writes one per year, since
    a multi-decade CDS request exceeds the per-request cost limit).

    Deliberately NOT xr.open_mfdataset: it hands the arrays to a chunk manager and hard-fails
    with "unrecognized chunk manager dask" unless dask is installed, which it is not here. A
    region-season of hourly 2m temperature is ~3 MB/year and a few hundred MB for a whole
    panel, so it fits in memory and concatenating eagerly is both simpler and one dependency
    lighter. (This is why this module had never actually run end-to-end.)"""
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"no hourly files match {pattern}")
    if len(files) == 1:
        return _open_one(files[0])
    return xr.concat([_open_one(f) for f in files], dim="time").sortby("time")


def daily_tmax(ds: xr.Dataset, region_reduce=("latitude", "longitude")) -> xr.DataArray:
    """Region-mean daily maximum 2m temperature in C.

    Order matters: we take the daily MAX per cell first, then the region MEAN of those maxima.
    Meaning 'the typical peak across the belt on that day' — not 'the hottest pixel anywhere',
    which would let one grid cell invent a heatwave for the whole region."""
    t = ds["t2m"] - 273.15
    per_cell_daily_max = t.resample(time="1D").max()
    return per_cell_daily_max.mean(dim=[d for d in region_reduce if d in per_cell_daily_max.dims])


def heat_event_by_year(tmax: xr.DataArray, months: list[int], threshold_c: float) -> list[dict]:
    """Acute-heat metrics per year over the season window."""
    sub = tmax.sel(time=tmax["time.month"].isin(months))
    years = sub["time"].dt.year
    out = []
    for yr in np.unique(years.values):
        v = np.asarray(sub.sel(time=years == yr).values, dtype=float)
        v = v[~np.isnan(v)]
        if v.size == 0:
            continue
        hot = v >= threshold_c
        # longest consecutive run of hot days
        spell = best = 0
        for h in hot:
            spell = spell + 1 if h else 0
            best = max(best, spell)
        out.append({
            "year": int(yr),
            "hot_days": int(hot.sum()),
            "extreme_days": int((v >= threshold_c + 5).sum()),
            "max_spell": int(best),
            "hottest_day_c": round(float(v.max()), 2),
            "degree_days": round(float(np.clip(v - threshold_c, 0, None).sum()), 1),
            "mean_tmax_c": round(float(v.mean()), 2),
        })
    return out
