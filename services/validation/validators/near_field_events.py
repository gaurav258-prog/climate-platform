"""Near-field event validators — hazard score vs the real catalogued events around each location.

Discrimination-kind: does a higher hazard score actually carry more observed near-field events? Reuses the
data loaders + binned spatial join already in services/intelligence/model_validation.py (single source of the
numerics). Honest labelling: this is an IN-SAMPLE faithfulness test — a catalogue-derived score checked
against its own record — not an out-of-sample forecast (that needs frozen scores + a temporal holdout, a
separate validator to add later). The 25 km radius is deliberate: a wider felt radius saturates at cell
resolution and measures nothing.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy.orm import Session

from services.intelligence.model_validation import _event_counts, _load_cells, _load_events
from services.validation.engine import ValidationResult, register

RADIUS_KM = 25.0


def _near_field(peril: str, source: str):
    def run(session: Session) -> ValidationResult:
        lat, lon, score, cells = _load_cells(session, peril)
        ev_lat, ev_lon, window_years = _load_events(session, peril)
        counts = (_event_counts(lat, lon, ev_lat, ev_lon, RADIUS_KM)
                  if len(ev_lat) else np.zeros(len(score)))
        return ValidationResult(
            hazard_type=peril, kind="discrimination",
            predicted=score.tolist(), observed=counts.tolist(), labels=cells,
            target_source=source, scope="global", method="in_sample",
            data_vintage=f"{window_years}y catalogue",
            notes=(f"hazard score vs near-field (≤{RADIUS_KM:.0f} km) catalogue events over ~{window_years}y; "
                   f"in-sample faithfulness, not an out-of-sample forecast"),
        )
    return run


register("seismic")(_near_field("seismic", "USGS/EMSC seismic catalogue (M≥5)"))
register("storm")(_near_field("storm", "NOAA IBTrACS storm tracks"))
