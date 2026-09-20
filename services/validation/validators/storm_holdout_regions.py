"""All-basin storm holdout — does the tropical-cyclone score rank land/coastal locations in EVERY basin, not just where the
stored channel happens to hold cells (which is Latin America & the Caribbean; see storm_holdout.py).

PRE-REGISTERED DESIGN (fixed before any result was computed; no tuning afterwards):
  • Locations: a 1° grid over 40°S–45°N, kept only where ml.validation.regional.macro_region() assigns a macro-region
    (land, or within ~1° of a coast) — the places assets actually sit. Nothing depends on what is stored in canonical_scores.
  • Predicted: the production on-demand score `storm_return_level_score(lat, lon, max_season=HOLDOUT_FROM-1)` — the 1-in-10-year
    wind rebuilt from seasons BEFORE the holdout, exactly as storm_oos does. Cells with no earlier storm (score 0) are dropped.
  • Observed: peak wind of IBTrACS storms from HOLDOUT_FROM (2003) on within RADIUS_KM of the location (same near field as
    storm_oos); cells no storm reached are dropped. 24 held-out seasons ≥ the 10-year return period.
  • Sampling: at most PER_REGION_CAP locations per macro-region, fixed seed, so one big region cannot dominate.
  • Test: rank, Spearman ≥ 0.35 pooled; per macro-region judged by ml.validation.regional.stratified_report (n ≥ 20, ρ ≥ 0.35).
Known limits: wind intensity, not damage; IBTrACS agency wind differs by basin (averaging periods); score and target come
from the same track record, so this is a temporal (not source-independent) holdout.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register
from services.validation.validators.storm_severity import RADIUS_KM, _peak_intensity_near

HOLDOUT_FROM = 2003
PER_REGION_CAP = 800
SEED = 11
LAT_RANGE = (-40, 45)


def _candidates():
    from ml.validation.regional import macro_region
    pts = []
    for la in range(LAT_RANGE[0], LAT_RANGE[1] + 1):
        for lo in range(-180, 180):
            r = macro_region(float(la), float(lo))
            if r:
                pts.append((float(la), float(lo), r))
    return pts


def _cap_per_region(pts: list, cap: int, seed: int) -> list:
    """At most `cap` points per region label (last tuple element), seeded, order-stable."""
    rng = np.random.default_rng(seed)
    out = []
    for reg in sorted({p[-1] for p in pts}):
        mine = [p for p in pts if p[-1] == reg]
        if len(mine) > cap:
            keep = np.sort(rng.choice(len(mine), cap, replace=False))
            mine = [mine[i] for i in keep]
        out += mine
    return out


def _run(session: Session) -> ValidationResult:
    from ml.scoring.storm_return_level import storm_return_level_score
    rows = session.execute(text("SELECT CAST(lat AS FLOAT), CAST(lon AS FLOAT), CAST(max_wind_kt AS FLOAT) FROM storm_events "
                                "WHERE max_wind_kt IS NOT NULL AND season_year >= :y"), {"y": HOLDOUT_FROM}).all()
    ev = np.array(rows, float)
    pts = _candidates()
    la = np.array([p[0] for p in pts]); lo = np.array([p[1] for p in pts])
    peak = _peak_intensity_near(la, lo, ev[:, 0], ev[:, 1], ev[:, 2], RADIUS_KM)
    hit = [p + (float(pk),) for p, pk in zip(pts, peak) if pk > 0]          # (lat, lon, region, peak)
    sample = _cap_per_region([(a, b, pk, r) for a, b, r, pk in hit], PER_REGION_CAP, SEED)
    pred, obs, strata, labels = [], [], [], []
    for a, b, pk, r in sample:
        sc = storm_return_level_score(a, b, max_season=HOLDOUT_FROM - 1)["score"]
        if sc and sc > 0:
            pred.append(float(sc)); obs.append(float(pk)); strata.append(r); labels.append(f"{a:.0f},{b:.0f}")
    return ValidationResult(
        hazard_type="storm", kind="rank", predicted=pred, observed=obs, labels=labels, strata=strata,
        target_source=f"NOAA IBTrACS peak wind, seasons {HOLDOUT_FROM}+ (held out), all basins, 1° land/coast grid",
        scope="global_allbasin", method="temporal_holdout", data_vintage=f"IBTrACS 1981–2026; ≤{PER_REGION_CAP}/region, seed {SEED}",
        notes=("1-in-10-year wind from seasons ≤2002 vs peak wind of 2003+ storms within "
               f"{RADIUS_KM:.0f} km, at land/coastal 1° points in every macro-region; pre-registered design in the module docstring"))


register("storm_oos_allbasin")(_run)
