"""Temporal-holdout validator — the stronger, forecast-oriented test.

In-sample faithfulness asks "does the score reflect the record we hold?". The harder question a supervisor
asks is "does it predict what it hadn't seen?". This validator holds out the most recent window of the event
catalogue and tests whether today's standing score discriminates WHERE those held-out events then occurred —
out-of-sample in time. A score that only memorised its own history would pass the in-sample test but fail
here; a genuinely skilful one passes both. Method is labelled `temporal_holdout` so the record shows exactly
what kind of test each number is.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.model_validation import _event_counts, _load_cells
from services.validation.engine import ValidationResult, register

HOLDOUT_FROM_YEAR = 2019   # test against events in the most recent window
RADIUS_KM = 25.0


def _run(session: Session) -> ValidationResult:
    lat, lon, score, cells = _load_cells(session, "seismic")
    rows = session.execute(text(
        "SELECT CAST(epicentre_lat AS FLOAT), CAST(epicentre_lon AS FLOAT) FROM seismic_events "
        "WHERE CAST(magnitude AS FLOAT) >= 5 AND EXTRACT(YEAR FROM origin_time) >= :y"),
        {"y": HOLDOUT_FROM_YEAR}).all()
    ev_lat = np.array([r[0] for r in rows]); ev_lon = np.array([r[1] for r in rows])
    counts = (_event_counts(lat, lon, ev_lat, ev_lon, RADIUS_KM) if len(ev_lat) else np.zeros(len(score)))
    return ValidationResult(
        hazard_type="seismic", kind="discrimination",
        predicted=score.tolist(), observed=counts.tolist(), labels=cells,
        target_source=f"USGS/EMSC seismic (M≥5), holdout {HOLDOUT_FROM_YEAR}+",
        scope="global", method="temporal_holdout", data_vintage=f"events {HOLDOUT_FROM_YEAR}+",
        notes=(f"standing score vs held-out events from {HOLDOUT_FROM_YEAR}+ — out-of-sample in time "
               f"(forecast-oriented), the stronger test than in-sample faithfulness"),
    )


register("seismic_oos")(_run)
