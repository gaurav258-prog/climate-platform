"""Storm severity, held out in time — the forecast-oriented test for the tropical-cyclone channel.

The in-sample severity test asks whether the score tracks the peak intensity of storms already in the record.
This holds out the most recent seasons and asks the harder question: does today's standing score rank locations
by the peak intensity of storms that came AFTER the record the field was built on? Same ruler as the in-sample
test (rank skill on observed max wind among locations a storm reached), method labelled `temporal_holdout`.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.model_validation import _load_cells
from services.validation.engine import ValidationResult, register
from services.validation.validators.storm_severity import RADIUS_KM, _peak_intensity_near

HOLDOUT_FROM_YEAR = 2019


MIN_SEASONS = 20     # a spatial holdout of rare extremes needs a long record; a 10-season table cannot hold out fairly


def _run(session: Session) -> ValidationResult:
    lat, lon, score, cells = _load_cells(session, "storm")
    y0, y1, basins = session.execute(text("SELECT min(season_year), max(season_year), count(DISTINCT basin) FILTER (WHERE season_year >= :y) FROM storm_events"),
                                     {"y": HOLDOUT_FROM_YEAR}).first()
    if y0 is None or (y1 - y0 + 1) < MIN_SEASONS or (basins or 0) < 2:
        # Not testable on this record: say so on the ledger rather than grade a skewed sample. The result carries no
        # samples, so the engine records INSUFFICIENT with the reason.
        return ValidationResult(hazard_type="storm", kind="rank", predicted=[], observed=[], labels=[],
                                target_source=f"NOAA IBTrACS peak wind, seasons {HOLDOUT_FROM_YEAR}+ (held out)", scope="global", method="temporal_holdout",
                                data_vintage=f"storm record {y0}–{y1}, {basins or 0} basin(s) in the holdout window",
                                notes=(f"temporal holdout not applicable: the storm_events record spans {(y1 - y0 + 1) if y0 else 0} seasons and the "
                                       f"holdout window covers {basins or 0} basin(s); a fair spatial holdout of rare extremes needs ≥{MIN_SEASONS} seasons "
                                       f"across basins (ingest the full IBTrACS record, 1980+). The in-sample severity test remains the current evidence."))
    rows = session.execute(text("SELECT CAST(lat AS FLOAT), CAST(lon AS FLOAT), CAST(max_wind_kt AS FLOAT) FROM storm_events "
                                "WHERE max_wind_kt IS NOT NULL AND season_year >= :y"), {"y": HOLDOUT_FROM_YEAR}).all()
    ev_lat = np.array([r[0] for r in rows]); ev_lon = np.array([r[1] for r in rows]); ev_int = np.array([r[2] for r in rows])
    peak = _peak_intensity_near(lat, lon, ev_lat, ev_lon, ev_int, RADIUS_KM) if len(ev_lat) else np.zeros(len(score))
    hit = peak > 0
    # the honest predictor is the score the record would have given BEFORE the holdout window: rebuilt here from
    # seasons ≤ HOLDOUT_FROM_YEAR-1 for every hit cell (the standing score already includes the held-out storms)
    from scripts.score_point_on_demand import storm_score_at
    idx = np.where(hit)[0]
    pred = np.array([storm_score_at(float(lat[i]), float(lon[i]), max_season=HOLDOUT_FROM_YEAR - 1)[0] for i in idx])
    keep = pred > 0                                     # a cell with no storm on the earlier record has no prediction to test
    return ValidationResult(hazard_type="storm", kind="rank", predicted=pred[keep].tolist(), observed=peak[idx][keep].tolist(),
                            labels=[cells[i] for i, k in zip(idx, keep) if k], target_source=f"NOAA IBTrACS peak wind, seasons {HOLDOUT_FROM_YEAR}+ (held out)",
                            scope="global", method="temporal_holdout", data_vintage=f"storm seasons {HOLDOUT_FROM_YEAR}+",
                            notes=f"storm score rebuilt from seasons ≤{HOLDOUT_FROM_YEAR - 1} vs observed peak intensity of storms from {HOLDOUT_FROM_YEAR}+ within ≤{RADIUS_KM:.0f} km — out of sample in time")


register("storm_oos")(_run)
