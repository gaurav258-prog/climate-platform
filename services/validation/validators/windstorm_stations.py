"""Windstorm validator against station-measured gusts — the production windstorm channel vs what anemometers recorded.

PRE-REGISTERED DESIGN (fixed before any result was computed; do not tune after seeing the ledger row):
  • Truth: NOAA ISD hourly gusts, 100 stations (60 CONUS / 40 Europe), 2010–2023, data/windstorm_station_val/
    annual_max_gust_station_year.csv. A station-year counts only if ≥80 % of hours are present.
  • Observed = MEDIAN annual-maximum gust per station, EXCLUDING 2016 (2016 completeness was the station-selection
    filter, so it is not independent of how stations were chosen). Stations need ≥ MIN_YEARS usable years.
  • Predicted = the production windstorm score (ml.scoring.windstorm_point: ERA5 mean-gust climatology → 0–100 anchor)
    at the station's nearest 0.5° cell — i.e. exactly what a customer sees, worldwide, not a research field.
  • Test: rank (Spearman ≥ 0.35 gate), pooled with per-macro-region strata; `_us` / `_eu` keys score each region alone.
  • Secondary, reported in metrics only (never gated): mean annual max, and — at CONUS stations — the synoptic
    convective/tropical-filtered return level (data/wind/windstorm_synoptic_conus.npz) vs the same observed value.
Known limits (disclosed): ISD logs a gust only when notable (~22 % CONUS / ~17 % Europe of hours), so annual maxima are
biased low where gusts are rarely logged; Europe coverage is thin (no DE/NL/DK); station maxima in CONUS include
convective and tropical gusts that a monthly-mean-gust climatology cannot see.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

CSV = Path("data/windstorm_station_val/annual_max_gust_station_year.csv")
SYNOPTIC = Path("data/wind/windstorm_synoptic_conus.npz")
MIN_COMPLETENESS = 0.80
EXCLUDE_YEARS = (2016,)
MIN_YEARS = 12


def _station_table():
    import pandas as pd
    df = pd.read_csv(CSV)
    df = df[(df.completeness >= MIN_COMPLETENESS) & ~df.year.isin(EXCLUDE_YEARS) & df.annmax_ms.notna()]
    g = df.groupby("station").agg(n=("year", "size"), obs=("annmax_ms", "median"), mean_am=("annmax_ms", "mean"),
                                  lat=("LAT", "first"), lon=("LON", "first"), name=("name", "first"), region=("region", "first"))
    return g[g.n >= MIN_YEARS].reset_index()


def _make(region: str | None):
    def run(session: Session) -> ValidationResult:
        from ml.scoring import windstorm_point as W
        from ml.validation.regional import macro_region
        scope = {None: "US+EU", "CONUS": "US", "EUROPE": "EU"}[region]
        if not CSV.exists():
            return ValidationResult(hazard_type="windstorm", kind="rank", predicted=[], observed=[], target_source="NOAA ISD station gusts",
                                    scope=scope, method="out_of_sample", notes="data/windstorm_station_val missing")
        t = _station_table()
        if region:
            t = t[t.region == region]
        pred, keep = [], []
        for i, r in enumerate(t.itertuples()):
            g = W._gust(float(r.lat), float(r.lon))
            if g is None or not np.isfinite(g):
                continue                                    # channel does not score this cell: absent, never filled
            pred.append(float(W._anchor(float(g))))
            keep.append(i)
        t = t.iloc[keep].reset_index(drop=True)
        extra = {"min_years": MIN_YEARS, "excluded_years": list(EXCLUDE_YEARS), "n_stations": int(len(t))}
        from scipy.stats import spearmanr
        if len(t) >= 5:
            extra["rho_mean_annual_max"] = round(float(spearmanr(pred, t.mean_am)[0]), 4)
            if SYNOPTIC.exists():
                z = np.load(SYNOPTIC)
                us = t[t.region == "CONUS"]
                if len(us) >= 5:
                    ii = [int(np.abs(z["lat"] - la).argmin()) for la in us.lat]
                    jj = [int(np.abs(z["lon"] - lo).argmin()) for lo in us.lon]
                    extra["conus_synoptic_rho"] = round(float(spearmanr([float(z["gust_ms"][a, b]) for a, b in zip(ii, jj)], us.obs)[0]), 4)
                    extra["conus_synoptic_n"] = int(len(us))
                    extra["conus_production_rho"] = round(float(spearmanr([p for p, rg in zip(pred, t.region) if rg == "CONUS"], us.obs)[0]), 4)
        sha = hashlib.sha256(CSV.read_bytes()).hexdigest()[:12]
        return ValidationResult(
            hazard_type="windstorm", kind="rank", predicted=pred, observed=[float(x) for x in t.obs],
            labels=[f"{r.station} {r.name}" for r in t.itertuples()],
            strata=[macro_region(float(r.lat), float(r.lon)) for r in t.itertuples()],
            target_source="NOAA ISD hourly gusts 2010–2023: median annual-max gust per station (2016 excluded)",
            scope=scope, method="out_of_sample", data_vintage=f"{len(t)} stations ≥{MIN_YEARS}y; csv {sha}",
            notes=("production windstorm score at the station cell vs the median annual-maximum gust the station recorded; pre-registered "
                   "design in the module docstring. Limits: ISD logs gusts only when notable; thin Europe; CONUS maxima include convective/tropical gusts."),
            extra=extra)
    return run


register("windstorm_stations")(_make(None))
register("windstorm_stations_us")(_make("CONUS"))
register("windstorm_stations_eu")(_make("EUROPE"))
