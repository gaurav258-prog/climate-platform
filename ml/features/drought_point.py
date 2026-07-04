"""
On-demand drought feature fetch + climatology lookup for an arbitrary point --
the drought counterpart flagged as follow-on work in
scripts/score_point_gridded_on_demand.py's docstring (heat's counterpart,
ml/features/heat_point.py, was built first and is mirrored here).

DISCLOSED SCOPE SIMPLIFICATION -- SPI-1, NOT SPI-3
====================================================
ml/features/drought.py's SPI/SPEI (the batch/backtest path, model_version
"drought-spei-v0" in model_registry) is a z-score of a ROLLING N-MONTH
(default 3-month, i.e. "SPI-3") precipitation ACCUMULATION against a baseline
mean/std computed for that SAME rolling sum across 1991-2020. That baseline
statistic (mean/std of a 3-month rolling sum) is fundamentally different from
what climatology_baseline stores: precip_mean_mm/precip_std_mm there is the
mean/std of the SINGLE calendar month's MEAN DAILY precipitation rate
(mm/day), not a multi-month rolling sum. Reconstructing the correct SPI-3
baseline would require re-deriving a rolling-sum climatology from raw 30-year
daily/monthly data -- not available in this on-demand session (climatology_
baseline only has the single-month statistic).

So this module deliberately computes a SIMPLER, honestly-labeled v0: a
single-month precipitation-rate anomaly z-score, i.e. "SPI-1" --

    z = (recent_actual_precip_rate_mm_day - precip_mean_mm) / precip_std_mm

using a trailing ~30-day precipitation rate for the query point vs. the
CURRENT calendar month's single-month baseline. This is the SAME "disclosed
approximation, not silently redefined as the full standard" convention
ml/features/drought.py itself already uses for its Gaussian-vs-gamma-fit
standardization -- SPI-1 is a real, commonly-used member of the SPI family
(McKee et al. 1993 define SPI at multiple accumulation windows, 1-month
included), just a shorter, noisier window than the SPI-3 the batch model
uses. It is NOT the batch model's SPI-3 and must never be presented as such;
model_version below is a distinct string ("drought-spi1-on-demand-v0") for
exactly this reason -- see scripts/drought_score_on_demand.py.

McKEE ET AL. 1993 SEVERITY CLASSIFICATION
==========================================
McKee, T.B., Doesken, N.J., Kleist, J. (1993), "The relationship of drought
frequency and duration to time scales," 8th Conference on Applied
Climatology, American Meteorological Society -- the original SPI paper and
the standard, citable severity classification (same "named real thresholds"
convention as ml/scoring/pollution_aqi.py's WHO AQG breakpoints):

    SPI >= 2.0            extremely wet
    1.5 <= SPI < 2.0       very wet
    1.0 <= SPI < 1.5       moderately wet
   -0.99 <= SPI < 1.0      near normal
   -1.49 <= SPI < -1.0     moderately dry
   -1.99 <= SPI < -1.5     severely dry
    SPI <= -2.0            extremely dry

`spi_to_drought_score` below linearly interpolates a 0-100 DROUGHT score
between these named anchors: z >= 0 (near-normal-or-wetter) -> 0, z == -1.0
-> ~50, z <= -2.0 -> 100 (capped, not extrapolated) -- the same "cap beyond
the worst named milestone" convention as pollution_aqi.py's IT-1 cap.
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

FEATURE_COLS = ["precip_recent_mm_day"]
H3_RES = 8
TRAILING_WINDOW_DAYS = 30  # ~30-day trailing precip rate, compared to the month's daily-rate baseline
CLIMATOLOGY_BOX_DEG = 1.0  # bounded lat/lon box for the nearest-neighbor climatology query
ERA5_LAND_LAG_DAYS = 7  # CORRECTED during wiring: this file's original docstring/comments claimed
# "ERA5-Land's on-demand fetch has not hit a 'today rejected' publish-lag error in this project's
# live tests" (mirroring flood/wildfire's assumption). That claim was live-disproved by the heat
# builder on 2026-07-04: a bare date.today() request to reanalysis-era5-land was REJECTED with
# MultiAdaptorNoDataError ("latest date available: 2026-06-29", i.e. today - 5 days). Drought hits
# the SAME dataset/adaptor (reanalysis-era5-land) via fetch_era5_precip, so it is subject to the
# identical publish lag. Applying the same margin ml/features/heat_point.py and services/ingestion/
# adapters/era5.py's ERA5Adapter already use ("ERA5 lags ~5 days; default to 7 days ago to be safe").

DROUGHT_MODEL_VERSION = "drought-spi1-on-demand-v0"

# McKee et al. 1993 SPI severity anchors: (spi, drought_score_0_100), descending SPI.
# z >= 0 (near-normal or wetter) floors at 0; z <= -2.0 (extremely dry) caps at 100.
_MCKEE_ANCHORS: list[tuple[float, float]] = [
    (0.0, 0.0),
    (-1.0, 50.0),
    (-1.5, 75.0),
    (-2.0, 100.0),
]


def spi_to_drought_score(spi: float) -> float:
    """Map an SPI (or SPI-1-style single-month anomaly) z-score to a 0-100
    DROUGHT score via linear interpolation between the McKee et al. 1993 named
    severity anchors (0=no drought/wet, 100=extreme drought). Capped at the
    extremes, not extrapolated beyond them."""
    if spi >= _MCKEE_ANCHORS[0][0]:
        return 0.0
    if spi <= _MCKEE_ANCHORS[-1][0]:
        return 100.0
    for (spi_hi, score_lo), (spi_lo, score_hi) in zip(_MCKEE_ANCHORS, _MCKEE_ANCHORS[1:]):
        if spi_lo <= spi <= spi_hi:
            frac = (spi_hi - spi) / (spi_hi - spi_lo)
            return round(score_lo + frac * (score_hi - score_lo), 1)
    return 100.0  # unreachable, defensive


def fetch_era5_precip(area: list[float], end_day: date = None,
                       window: int = TRAILING_WINDOW_DAYS) -> xr.Dataset:
    """One CDS request for the `window`-day run-up to `end_day` over `area`
    [N,W,S,E], variable total_precipitation -- same request shape as
    flood_era5.fetch_era5, just precip-only and a ~30-day window instead of
    flood's 8-day window (drought is a slow-onset deficit signal, not a
    flash-flood one). CORRECTED during wiring: ERA5-Land's on-demand fetch DOES
    hit a "today rejected" publish-lag error (MultiAdaptorNoDataError, latest
    available = today - 5 days, confirmed live 2026-07-04 by the heat builder
    against this same dataset/adaptor) -- callers should pass an `end_day`
    already offset by ERA5_LAND_LAG_DAYS (this function's own fallback below
    does so too, when `end_day` isn't supplied)."""
    import cdsapi
    end_day = end_day or (date.today() - timedelta(days=ERA5_LAND_LAG_DAYS))
    days = [end_day - timedelta(days=k) for k in range(window)]
    c = cdsapi.Client(quiet=True)
    tmp = tempfile.NamedTemporaryFile(suffix=".nc", delete=False)
    tmp.close()
    c.retrieve("reanalysis-era5-land", {
        "variable": ["total_precipitation"],
        "year": sorted({str(d.year) for d in days}),
        "month": sorted({f"{d.month:02d}" for d in days}),
        "day": sorted({f"{d.day:02d}" for d in days}),
        "time": ["23:00"],  # ERA5-Land accumulates from 00 UTC; 23:00 = the day's total (flood_era5 convention)
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


def compute_features(ds: xr.Dataset, window: int = TRAILING_WINDOW_DAYS) -> pd.DataFrame:
    """ERA5-Land dataset -> one row per H3 cell with the trailing-window mean
    DAILY precip rate (mm/day). Sums the daily totals (same summing pattern as
    flood_era5.compute_features's precipitation_7d_mm) then divides by the
    number of days actually present, so it's comparable to climatology_
    baseline's precip_mean_mm, which is a DAILY rate, not a window total."""
    tvar = "valid_time" if "valid_time" in ds else "time"
    lat = ds["latitude"].values
    lon = ds["longitude"].values
    tp = ds["tp"]
    n_days = tp.sizes[tvar] if tvar in tp.dims else 1
    tp_sum_mm = (tp.sum(dim=tvar) * 1000.0).values if tvar in tp.dims else (tp * 1000.0).values

    rows = []
    for i, la in enumerate(lat):
        for j, lo in enumerate(lon):
            if np.isnan(tp_sum_mm[i, j]):
                continue
            rows.append({
                "h3_cell": h3.latlng_to_cell(float(la), float(lo), H3_RES),
                "precip_recent_mm_day": float(tp_sum_mm[i, j]) / max(n_days, 1),
            })
    return pd.DataFrame(rows).groupby("h3_cell", as_index=False).agg(
        precip_recent_mm_day=("precip_recent_mm_day", "mean"))


def _nearest_climatology(lat: float, lon: float, month: int) -> dict | None:
    """Bounded-box + in-Python nearest-neighbor lookup against
    climatology_baseline -- identical convention to heat_point.py's
    _nearest_climatology (12.3M rows total, never a full-table scan: filter
    by month first, then a +/-1deg lat/lon box, then closest by great-circle
    distance in Python; no PostGIS nearest-neighbor index on this table)."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT h3_cell, precip_mean_mm, precip_std_mm, lat, lon
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
        "precip_mean_mm": float(best["precip_mean_mm"]),
        "precip_std_mm": float(best["precip_std_mm"]),
        "lat": float(best["lat"]),
        "lon": float(best["lon"]),
    }


def fetch_and_score(lat: float, lon: float, area: list[float] = None,
                     end_day: date = None) -> pd.DataFrame:
    """Fetch the trailing ~30-day ERA5-Land precip rate for a small bbox
    around (lat, lon), look up the matching climatology_baseline cell
    (nearest-neighbor, bounded-box) for the query month, compute the SPI-1
    z-score and its 0-100 McKee-anchored drought score. Returns a DataFrame
    with one row per H3 cell: h3_cell, precip_recent_mm_day, clim_mean_mm,
    clim_std_mm, spi1, score. Rows whose bbox neighborhood has no
    climatology match are dropped (can't score without a baseline)."""
    end_day = end_day or (date.today() - timedelta(days=ERA5_LAND_LAG_DAYS))
    if area is None:
        area = [lat + 0.5, lon - 0.5, lat - 0.5, lon + 0.5]

    ds = fetch_era5_precip(area, end_day)
    df = compute_features(ds)
    ds.close()
    if df.empty:
        return df

    month = end_day.month
    results = []
    for r in df.itertuples():
        cell_lat, cell_lon = h3.cell_to_latlng(r.h3_cell)
        clim = _nearest_climatology(cell_lat, cell_lon, month)
        if clim is None:
            continue
        std = clim["precip_std_mm"]
        if std <= 0:
            continue  # can't z-score against a zero/degenerate std (e.g. perpetually-dry desert cell)
        spi1 = (r.precip_recent_mm_day - clim["precip_mean_mm"]) / std
        score = spi_to_drought_score(spi1)
        results.append({
            "h3_cell": r.h3_cell,
            "precip_recent_mm_day": round(float(r.precip_recent_mm_day), 3),
            "clim_mean_mm": round(clim["precip_mean_mm"], 3),
            "clim_std_mm": round(clim["precip_std_mm"], 3),
            "climatology_cell": clim["h3_cell"],
            "spi1": round(spi1, 2),
            "score": score,
        })
    return pd.DataFrame(results)
