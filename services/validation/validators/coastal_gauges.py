"""Coastal-flood validators — the site extreme-still-water term against what tide gauges recorded (GESLA-3 /
NOAA CO-OPS), on the ledger.

The v3 coastal-flood channel reads the observed 1-in-10-year extreme still-water level at the nearest tide gauge
(ml/scoring/coastal_extreme_water.py). Three questions, each a `rank` test (Spearman ≥ 0.35 + monotone bands):

  coastal_ewl_holdout  Held out in time. The level rebuilt from gauge years ≤ HOLDOUT_BEFORE only, against the
                       maximum the same gauge then recorded in the following window (≥ RETURN_PERIOD years of it).
                       Does yesterday's 1-in-10 level rank where the sea went highest afterwards? Global.
  coastal_ewl_logo     Leave-one-gauge-out in space. Each gauge's level predicted from its nearest OTHER gauge
                       within GAUGE_RADIUS_KM, against its own observed level: the test every cell without its own
                       gauge relies on. Global.
  coastal_score_coops  The channel's score itself at NOAA CO-OPS gauges (level from GESLA years ≤ 2013, DEM
                       elevation at the gauge) against the CO-OPS verified 2014–2023 maximum above MSL — the
                       independent US target the v2 constant scored −0.32 on. Needs data/coastal_val/
                       coops_monthly_extremes.csv (scripts/fetch_coops_extremes.py); absent → INSUFFICIENT.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from ml.scoring.coastal_extreme_water import (
    GAUGE_RADIUS_KM,
    MIN_YEARS,
    RETURN_PERIOD_YEARS,
    gauge_levels,
    nearest_gauge,
)
from ml.scoring.sea_level import _score
from services.validation.engine import ValidationResult, register


def _as_score(level_m: float) -> float:
    """The level expressed as the channel would at the shoreline (elevation 0, no SLR): rank-identical to the level
    in metres, but on the 0–100 scale the ledger's severity bands are defined on."""
    return round(_score(0.0, 0.0, ewl_m=level_m), 2)


HOLDOUT_BEFORE = int(os.environ.get("COASTAL_HOLDOUT_BEFORE", "2010"))   # level from ≤2010, observed 2011–2020
COOPS_CSV = Path("data/coastal_val/coops_monthly_extremes.csv")
COOPS_ELEV = Path("data/coastal_val/coops_gauge_elev.json")
COOPS_MIN_MONTHS = 60
TARGET = "GESLA-3 tide-gauge observed extreme still-water level above mean sea level"


def _holdout(session: Session) -> ValidationResult:
    before = {g["record_id"]: g for g in gauge_levels(max_year=HOLDOUT_BEFORE, session=session)}
    # observed: the maximum above the SAME record's pre-window MSL in the window (the level is a pre-window quantity;
    # a post-window datum would let sea-level rise leak in as skill)
    rows = session.execute(text("""
        WITH yr AS (SELECT record_id, year, max(max_m) AS mx, count(*) AS n FROM tide_gauge_extremes
                    WHERE year > :y GROUP BY record_id, year),
             msl AS (SELECT record_id, avg(mean_m) AS msl FROM tide_gauge_extremes WHERE year <= :y GROUP BY record_id)
        SELECT yr.record_id, max(yr.mx - msl.msl) AS obs, count(*) AS n_years
        FROM yr JOIN msl USING (record_id) WHERE yr.n >= 9 GROUP BY yr.record_id
    """), {"y": HOLDOUT_BEFORE}).all()
    pred, obs, labels = [], [], []
    for rid, o, n in rows:
        if rid in before and n >= RETURN_PERIOD_YEARS:
            pred.append(_as_score(before[rid]["ewl_1in10_m"])); obs.append(float(o)); labels.append(f"{rid} ({before[rid]['country']})")
    return ValidationResult(hazard_type="coastal_flood", kind="rank", predicted=pred, observed=obs, labels=labels,
                            target_source=f"{TARGET}, years {HOLDOUT_BEFORE + 1}+ (held out)", scope="global", method="temporal_holdout",
                            data_vintage=f"GESLA-3 1979–{HOLDOUT_BEFORE} → observed {HOLDOUT_BEFORE + 1}–2020",
                            notes=(f"1-in-{RETURN_PERIOD_YEARS}-year level from gauge years ≤{HOLDOUT_BEFORE} (≥{MIN_YEARS} years) vs the maximum "
                                   f"the same gauge recorded in ≥{RETURN_PERIOD_YEARS} later years, both above the pre-window mean sea level"))


def _logo(session: Session) -> ValidationResult:
    levels = gauge_levels(session=session)
    pred, obs, labels = [], [], []
    for g in levels:
        other = nearest_gauge(g["lat"], g["lon"], levels, GAUGE_RADIUS_KM, exclude_record=g["record_id"])
        if other is None:
            continue
        pred.append(_as_score(other["ewl_1in10_m"])); obs.append(g["ewl_1in10_m"]); labels.append(f"{g['record_id']} ← {other['record_id']} {other['dist_km']} km")
    return ValidationResult(hazard_type="coastal_flood", kind="rank", predicted=pred, observed=obs, labels=labels,
                            target_source=TARGET, scope="global", method="out_of_sample",
                            data_vintage="GESLA-3 1979–2020", notes=(f"leave-one-gauge-out: each gauge's 1-in-10 level predicted from its nearest other gauge "
                                                                      f"within {GAUGE_RADIUS_KM:.0f} km vs its own observed level — the transfer every cell without a gauge relies on"))


def _coops(session: Session) -> ValidationResult:
    if not COOPS_CSV.exists():
        return ValidationResult(hazard_type="coastal_flood", kind="rank", predicted=[], observed=[], labels=[],
                                target_source="NOAA CO-OPS verified monthly extremes 2014–2023", scope="US", method="temporal_holdout",
                                notes=f"target file {COOPS_CSV} not present — run scripts/fetch_coops_extremes.py")
    import pandas as pd

    from ml.scoring.coastal_flood_point import _ZERO
    from ml.scoring.sea_level import coastal_flood_score
    d = pd.read_csv(COOPS_CSV)
    d = d[d.highest_m_above_mhhw > -1.0]
    d["above_msl"] = d.highest_m_above_mhhw - d.msl_m_above_mhhw
    st = d.groupby(["station", "name", "lat", "lon"]).agg(n=("above_msl", "size"), obs=("above_msl", "max")).reset_index()
    st = st[st.n >= COOPS_MIN_MONTHS]
    elev = _coops_elevations(st)
    levels = gauge_levels(max_year=2013, session=session)
    pred, obs, labels = [], [], []
    for r in st.itertuples():
        e = elev.get(str(r.station))
        g = nearest_gauge(float(r.lat), float(r.lon), levels)
        if e is None or g is None:
            continue
        sc = coastal_flood_score(float(e), 0.5, _ZERO, ewl_m=g["ewl_1in10_m"])[0]   # a gauge sits at the shoreline
        if sc is None:
            continue
        pred.append(sc); obs.append(float(r.obs)); labels.append(f"{r.station} {r.name}")
    return ValidationResult(hazard_type="coastal_flood", kind="rank", predicted=pred, observed=obs, labels=labels,
                            target_source="NOAA CO-OPS verified monthly highest water levels 2014–2023, above MSL", scope="US", method="temporal_holdout",
                            data_vintage="GESLA-3 gauge years ≤2013 → CO-OPS 2014–2023",
                            notes=("the channel's own score at each CO-OPS gauge (DEM elevation, site level from gauge years ≤2013) vs the "
                                   "gauge's observed 10-year maximum above MSL; the v2 generic 2.0 m constant scored −0.32 on this target"))


def _coops_elevations(st) -> dict:
    """DEM elevation at each CO-OPS gauge (Copernicus GLO-90 via Open-Meteo), cached to a small JSON next to the target."""
    cache = json.loads(COOPS_ELEV.read_text()) if COOPS_ELEV.exists() else {}
    missing = [r for r in st.itertuples() if str(r.station) not in cache]
    if missing:
        import urllib.request
        for i in range(0, len(missing), 100):
            chunk = missing[i:i + 100]
            la = ",".join(f"{r.lat:.5f}" for r in chunk); lo = ",".join(f"{r.lon:.5f}" for r in chunk)
            with urllib.request.urlopen(f"https://api.open-meteo.com/v1/elevation?latitude={la}&longitude={lo}", timeout=60) as resp:
                for r, e in zip(chunk, json.load(resp)["elevation"]):
                    cache[str(r.station)] = e
        COOPS_ELEV.write_text(json.dumps(cache, indent=0, sort_keys=True))
    return cache


register("coastal_ewl_holdout")(_holdout)
register("coastal_ewl_logo")(_logo)
register("coastal_score_coops")(_coops)
