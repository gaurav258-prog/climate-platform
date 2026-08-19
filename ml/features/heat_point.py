"""
On-demand heat feature fetch + climatology lookup for an arbitrary point — the
heat/drought counterpart flagged as follow-on work in
scripts/score_point_gridded_on_demand.py's docstring.

Mirrors flood_era5.py's fetch_era5 + compute_features split:
  fetch_era5_land(area)   — ONE CDS request, variable "2m_temperature", for
                            date.today() (same "no artificial date margin"
                            convention as flood/wildfire: ERA5-Land's on-demand
                            fetch has not hit a publish-lag rejection in this
                            project's live tests, unlike CAMS-forecast).
  compute_features(ds)    — per-H3-cell today's temp_c (K → °C, ds["t2m"] is
                            in Kelvin exactly like ml/features/drought.py's
                            `T = ds["t2m"] - 273.15` convention).

fetch_and_score(lat, lon) glues that to climatology_baseline (nearest-neighbor,
bounded-box, per-month — see that table's migration docstring) and calls
ml/scoring/heat_climatology.py's heat_score() UNCHANGED: this module only
supplies temp_c/clim_mean/clim_std, it does not reimplement heat physics.

Unit-conversion decision: heat_score(temp_c, clim_mean, clim_std, ...) takes
BOTH temperature args in the SAME units, and the T_COMFORT=25/T_SEVERE=31
thermal-stress band in ml/scoring/heat_climatology.py is only physically
sane in Celsius (25-31 Kelvin is absolute zero territory). scripts/
score_cocoa_heat.py — the only other caller of heat_score() in this codebase —
also passes Celsius (via ml/features/drought.py's `ds["t2m"] - 273.15`).
climatology_baseline.temp_mean_k/temp_std_k are named _k (Kelvin) explicitly,
so BOTH today's ERA5-Land reading AND the climatology mean must be converted
K → °C before calling heat_score(). The std-dev does NOT need an additive
offset (a Kelvin-to-Celsius conversion is a pure shift, and std is
shift-invariant) but IS converted here anyway for a trivial reason: the
Kelvin and Celsius stds are numerically IDENTICAL (subtracting a constant
273.15 doesn't change spread), so "converting" clim_std is a no-op that's
kept only for symmetry/clarity in the code, not because it changes the value.
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
from sqlalchemy import text

from core.db.session import get_session
from ml.scoring.heat_climatology import heat_score

FEATURE_COLS = ["temp_c"]
H3_RES = 8
KELVIN_OFFSET = 273.15
CLIMATOLOGY_BOX_DEG = 1.0  # bounded lat/lon box for the nearest-neighbor climatology query
ERA5_LAND_LAG_DAYS = 7  # empirically confirmed live (2026-07-04): a bare date.today()
# request to reanalysis-era5-land was REJECTED with MultiAdaptorNoDataError ("None of
# the data you have requested is available yet... latest date available: 2026-06-29"),
# i.e. today - 5 days. That contradicts this project's flood/wildfire on-demand
# scorers' comment claiming ERA5-Land's on-demand fetch has "not hit a today-rejected
# error" -- it clearly can, and did, on live testing. Applying the SAME margin
# services/ingestion/adapters/era5.py's ERA5Adapter already uses for exactly this
# publish-lag ("ERA5 lags ~5 days; default to 7 days ago to be safe"), rather than
# inventing a new number.


def fetch_era5_land(area: list[float], day: date = None) -> xr.Dataset:
    """One CDS request for a single day's 2m temperature over `area` [N,W,S,E].

    Fetches 4 synoptic hours (00/06/12/18 UTC), NOT a single snapshot — a real
    bug, found and fixed live (2026-07-04): a single "12:00" reading was being
    compared against climatology_baseline's temp_mean_k, which is ECMWF's
    "monthly mean of daily means" (confirmed empirically: requesting that same
    monthly-means dataset at "12:00" is REJECTED with MarsNoDataError — "00:00"
    is just how the archive labels an already-full-day-averaged value, not a
    midnight reading). Comparing an afternoon snapshot against a day-and-night
    average made EVERY sunny summer afternoon look like an extreme anomaly,
    everywhere, regardless of any real heatwave (caught on a real Frankfurt
    query: 37C afternoon vs 17.6C day-night July mean -> saturated to 100).
    Averaging the same 4 hours flood/wildfire already fetch makes "today" and
    the baseline comparable quantities — both a full-day mean, not a mean vs a
    peak.
    """
    import cdsapi
    day = day or date.today()
    c = cdsapi.Client(quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
    tmp.close()
    c.retrieve("reanalysis-era5-land", {
        "variable": ["2m_temperature"],
        "year": [str(day.year)],
        "month": [f"{day.month:02d}"],
        "day": [f"{day.day:02d}"],
        "time": ["00:00", "06:00", "12:00", "18:00"],
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
        os.unlink(path)
        path = out
    return xr.open_dataset(path)


def compute_features(ds: xr.Dataset) -> pd.DataFrame:
    """ERA5-Land dataset -> one row per H3 cell with today's MEAN temp_c across
    the 4 fetched hours — comparable to climatology_baseline's own day-and-
    night mean, not a single afternoon snapshot (see fetch_era5_land's
    docstring for why that distinction is load-bearing, not cosmetic)."""
    tvar = "valid_time" if "valid_time" in ds else "time"
    lat = ds["latitude"].values
    lon = ds["longitude"].values
    t2m = ds["t2m"]
    t2m_mean = (t2m.mean(dim=tvar).values if tvar in t2m.dims else t2m.values)

    rows = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            val_k = float(t2m_mean[i, j])
            if np.isnan(val_k):
                continue
            rows.append({
                "h3_cell": h3.latlng_to_cell(float(la), float(lo), H3_RES),
                "temp_c": val_k - KELVIN_OFFSET,
            })
    return pd.DataFrame(rows).groupby("h3_cell", as_index=False).agg(temp_c=("temp_c", "mean"))


def _nearest_climatology(lat: float, lon: float, month: int) -> dict | None:
    """Bounded-box + in-Python nearest-neighbor lookup against climatology_baseline.

    12.3M rows total -> never a full-table scan. Filter by month (partitions
    the table 12x) AND a +/-1deg lat/lon box first (climatology_baseline is at
    ERA5's native 0.25deg resolution, so a 1deg box always contains several
    candidate grid points even near the query's own cell), then pick the
    closest by great-circle distance in Python -- there's no PostGIS
    nearest-neighbor index on this table, same convention this project already
    uses for flood/pollution/wildfire's H3-grid-mismatch nearest-neighbor fill.
    """
    with get_session() as s:
        rows = s.execute(text("""
            SELECT h3_cell, temp_mean_k, temp_std_k, lat, lon
            FROM climatology_baseline
            WHERE month = :m
              AND lat BETWEEN :lat_min AND :lat_max
              AND lon BETWEEN :lon_min AND :lon_max
        """), {
            "m": month,
            "lat_min": lat - CLIMATOLOGY_BOX_DEG, "lat_max": lat + CLIMATOLOGY_BOX_DEG,
            "lon_min": lon - CLIMATOLOGY_BOX_DEG, "lon_max": lon + CLIMATOLOGY_BOX_DEG,
        }).mappings().all()

    if not rows:
        return None

    best = min(rows, key=lambda r: h3.great_circle_distance(
        (lat, lon), (float(r["lat"]), float(r["lon"])), unit="km"))
    return {
        "h3_cell": best["h3_cell"],
        "temp_mean_k": float(best["temp_mean_k"]),
        "temp_std_k": float(best["temp_std_k"]),
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
    }


def fetch_and_score(lat: float, lon: float, area: list[float] = None,
                     day: date = None, scenario: str = "baseline",
                     horizon: str = "current") -> pd.DataFrame:
    """Fetch today's ERA5-Land temp for a small bbox around (lat, lon), look up
    the matching climatology_baseline cell (nearest-neighbor, bounded-box) for
    the query month, and score each fetched cell with heat_score(). Returns a
    DataFrame with one row per H3 cell: h3_cell, temp_c, clim_mean_c,
    clim_std_c, score. Rows whose bbox neighborhood has no climatology match
    are dropped (can't score without a baseline).
    """
    day = day or (date.today() - timedelta(days=ERA5_LAND_LAG_DAYS))
    if area is None:
        area = [lat + 0.5, lon - 0.5, lat - 0.5, lon + 0.5]

    ds = fetch_era5_land(area, day)
    df = compute_features(ds)
    ds.close()
    if df.empty:
        return df

    month = day.month
    results = []
    for r in df.itertuples():
        cell_lat, cell_lon = h3.cell_to_latlng(r.h3_cell)
        clim = _nearest_climatology(cell_lat, cell_lon, month)
        if clim is None:
            continue
        clim_mean_c = clim["temp_mean_k"] - KELVIN_OFFSET
        clim_std_c = clim["temp_std_k"]  # Kelvin->Celsius shift doesn't change std spread
        score = heat_score(r.temp_c, clim_mean_c, clim_std_c, scenario=scenario, horizon=horizon,
                           lat=cell_lat)
        results.append({
            "h3_cell": r.h3_cell,
            "temp_c": round(float(r.temp_c), 2),
            "clim_mean_c": round(clim_mean_c, 2),
            "clim_std_c": round(clim_std_c, 3),
            "climatology_cell": clim["h3_cell"],
            "score": score,
        })
    return pd.DataFrame(results)
