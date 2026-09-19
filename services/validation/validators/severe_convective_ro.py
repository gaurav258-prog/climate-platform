"""Severe-convective (tornado / damaging-report) validator — READ-ONLY re-run of the anchor test.

Same test as scripts/anchor_convective_spc.py (NOAA SPC hail >= 1 in, severe wind >= 50 kt or unmeasured, tornado
reports; CONUS 0.25 deg cells; target = the cell saw a damaging report in >= half the years 2014-2023), but the
prediction is the PRODUCTION score (ml.scoring.severe_convective_point.damage_anchored_score / 100) read from the
already-written data/convective/convective_anchor.json. Nothing is refitted and nothing is written: the anchor
script must never be run for a ledger refresh because it overwrites that production scorer input. Only the ledger
row is produced (by the runner / engine), which carries the always-on monotone_check.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

GRID = Path("data/convective/convective_potential.npz")
CONUS = (24.5, 49.5, -124.5, -67.0)
TRAIN, TEST = (2000, 2013), (2014, 2023)
EVENT_PROB = 0.5   # gate copied from the anchor script: damaging event in >= half the test years


def _reports():
    import pandas as pd
    hail = pd.read_csv("data/convective/1955-2023_hail.csv", usecols=["yr", "mag", "slat", "slon"])
    wind = pd.read_csv("data/convective/1955-2023_wind.csv", usecols=["yr", "mag", "slat", "slon"])
    tor = pd.read_csv("data/convective/spc_tornadoes.csv", usecols=["yr", "slat", "slon"])
    df = pd.concat([hail[hail["mag"] >= 1.0], wind[(wind["mag"] >= 50) | (wind["mag"] == 0)], tor], ignore_index=True)
    return df[(df.yr >= TRAIN[0]) & (df.yr <= TEST[1]) & df.slat.between(CONUS[0], CONUS[1]) & df.slon.between(CONUS[2], CONUS[3])]


def annual_probability(df, years, lat, lon, la_i, lo_i, shape) -> np.ndarray:
    """share of years in which each cell has >= 1 report (identical to the anchor script's density())."""
    d = df[(df.yr >= years[0]) & (df.yr <= years[1])]
    ii = np.clip(np.round((d.slat.values - lat[la_i][0]) / (lat[la_i][1] - lat[la_i][0])).astype(int), 0, len(la_i) - 1)
    jj = np.clip(np.round((d.slon.values - lon[lo_i][0]) / (lon[lo_i][1] - lon[lo_i][0])).astype(int), 0, len(lo_i) - 1)
    hit = np.zeros(shape)
    for yr in range(years[0], years[1] + 1):
        m = d.yr.values == yr
        cnt = np.zeros(shape)
        np.add.at(cnt, (ii[m], jj[m]), 1)
        hit += cnt > 0
    return hit / (years[1] - years[0] + 1)


def _run(session: Session) -> ValidationResult:
    from ml.scoring.severe_convective_point import damage_anchored_score
    g = np.load(GRID)
    lat, lon, pot = g["lat"], g["lon"], g["potential"]
    la_i = np.where((lat >= CONUS[0]) & (lat <= CONUS[1]))[0]
    lo_i = np.where((lon >= CONUS[2]) & (lon <= CONUS[3]))[0]
    sub = pot[np.ix_(la_i, lo_i)]
    land = ~np.isnan(sub)
    te = annual_probability(_reports(), TEST, lat, lon, la_i, lo_i, sub.shape)
    x, y_te = sub[land], te[land]
    pred = [damage_anchored_score(float(v)) / 100.0 for v in x]   # production score, as a probability
    return ValidationResult(hazard_type="severe_convective", kind="discrimination", predicted=pred,
                            observed=[int(v >= EVENT_PROB) for v in y_te],
                            target_source=f"NOAA SPC hail ≥1 in / severe wind / tornado reports {TEST[0]}–{TEST[1]} (CONUS), damaging event in ≥ half the years",
                            scope="CONUS", method="temporal_holdout", data_vintage=f"{TRAIN[0]}–{TEST[1]}",
                            notes="read-only re-run: production anchored score vs held-out 2014–2023 SPC reports; no refit, anchor file untouched")


register("severe_convective_ro")(_run)
