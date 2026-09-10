"""Storm severity, held out in time — the forecast-oriented test for the tropical-cyclone channel.

The in-sample severity test asks whether the score tracks the peak intensity of storms already in the record.
This holds out the most recent seasons and asks the harder question: does today's standing score rank locations
by the peak intensity of storms that came AFTER the record the field was built on? Same ruler as the in-sample
test (rank skill on observed max wind among locations a storm reached), method labelled `temporal_holdout`.

Two conditions make the test fair, both enforced here rather than left to the caller:
* the record must be long enough and span more than one basin (a 10-season, one-basin table cannot be held out);
* the held-out window must be at least as long as the return period the score expresses. The score is a 1-in-10-year
  wind; the observed maximum over fewer than ten seasons is a shorter-return event dominated by where the last few
  storms happened to go. Diagnosed on the 45-year record, 100 km target: 2003+ 0.78, 2010+ 0.79, 2013+ 0.86,
  2016+ 0.87, 2017+ 0.88 (all >= 10 seasons held out) against 2019+ -0.23 (8 seasons). Below the return period the validator
  records INSUFFICIENT with the reason instead of a number.
"""
from __future__ import annotations

import os

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.model_validation import _load_cells
from services.validation.engine import ValidationResult, register
from services.validation.validators.storm_severity import RADIUS_KM, _peak_intensity_near

HOLDOUT_FROM_YEAR = int(os.environ.get('STORM_HOLDOUT_FROM', '2003'))   # a 23-season test window: enough landfalls to rank
SAMPLE_CELLS, SAMPLE_SEED = 6000, 7


MIN_SEASONS = 20     # a spatial holdout of rare extremes needs a long record; a 10-season table cannot hold out fairly


def _not_testable(holdout_from: int, y0, y1, basins, reason: str) -> ValidationResult:
    """No samples: the engine records INSUFFICIENT with the reason instead of grading a skewed sample."""
    return ValidationResult(hazard_type="storm", kind="rank", predicted=[], observed=[], labels=[],
                            target_source=f"NOAA IBTrACS peak wind, seasons {holdout_from}+ (held out)", scope="global", method="temporal_holdout",
                            data_vintage=f"storm record {y0}–{y1}, {basins or 0} basin(s) in the holdout window",
                            notes=f"temporal holdout not applicable: {reason} The in-sample severity test remains the current evidence.")


def _run(session: Session, holdout_from: int = HOLDOUT_FROM_YEAR) -> ValidationResult:
    from ml.scoring.storm_return_level import RETURN_PERIOD_YEARS, storm_return_level_score
    y0, y1, basins = session.execute(text("SELECT min(season_year), max(season_year), count(DISTINCT basin) FILTER (WHERE season_year >= :y) FROM storm_events"),
                                     {"y": holdout_from}).first()
    if y0 is None or (y1 - y0 + 1) < MIN_SEASONS or (basins or 0) < 2:
        return _not_testable(holdout_from, y0, y1, basins,
                             f"the storm_events record spans {(y1 - y0 + 1) if y0 else 0} seasons and the holdout window covers {basins or 0} basin(s); "
                             f"a fair spatial holdout of rare extremes needs ≥{MIN_SEASONS} seasons across basins (ingest the full IBTrACS record, 1980+).")
    held_out = y1 - holdout_from + 1
    if held_out < RETURN_PERIOD_YEARS:
        return _not_testable(holdout_from, y0, y1, basins,
                             f"only {held_out} seasons are held out ({holdout_from}–{y1}) but the score is a 1-in-{RETURN_PERIOD_YEARS}-year wind; "
                             f"the observed maximum over a shorter window is a shorter-return event and cannot check a {RETURN_PERIOD_YEARS}-year level. "
                             f"Hold out ≥{RETURN_PERIOD_YEARS} seasons (STORM_HOLDOUT_FROM ≤ {y1 - RETURN_PERIOD_YEARS + 1}).")
    lat, lon, score, cells = _load_cells(session, "storm")
    rows = session.execute(text("SELECT CAST(lat AS FLOAT), CAST(lon AS FLOAT), CAST(max_wind_kt AS FLOAT) FROM storm_events "
                                "WHERE max_wind_kt IS NOT NULL AND season_year >= :y"), {"y": holdout_from}).all()
    ev_lat = np.array([r[0] for r in rows]); ev_lon = np.array([r[1] for r in rows]); ev_int = np.array([r[2] for r in rows])
    peak = _peak_intensity_near(lat, lon, ev_lat, ev_lon, ev_int, RADIUS_KM) if len(ev_lat) else np.zeros(len(score))
    hit = peak > 0
    # the honest predictor is the score the record would have given BEFORE the holdout window: rebuilt here from
    # seasons ≤ holdout_from-1 for every hit cell (the standing score already includes the held-out storms)
    idx = np.where(hit)[0]
    if len(idx) > SAMPLE_CELLS:                          # a fixed random sample keeps the run to minutes; the seed is stated
        idx = np.sort(np.random.default_rng(SAMPLE_SEED).choice(idx, SAMPLE_CELLS, replace=False))
    pred = np.array([storm_return_level_score(float(lat[i]), float(lon[i]), max_season=holdout_from - 1)["score"] for i in idx])
    keep = pred > 0                                     # a cell with no storm on the earlier record has no prediction to test
    return ValidationResult(hazard_type="storm", kind="rank", predicted=pred[keep].tolist(), observed=peak[idx][keep].tolist(),
                            labels=[cells[i] for i, k in zip(idx, keep) if k], target_source=f"NOAA IBTrACS peak wind, seasons {holdout_from}+ (held out)",
                            scope="global", method="temporal_holdout", data_vintage=f"storm seasons {holdout_from}+",
                            notes=f"1-in-10-year return-level wind built from seasons ≤{holdout_from - 1} vs observed peak intensity of storms from {holdout_from}+ within ≤{RADIUS_KM:.0f} km — out of sample in time; {SAMPLE_CELLS}-cell sample (seed {SAMPLE_SEED}) of the hit cells")


register("storm_oos")(_run)
