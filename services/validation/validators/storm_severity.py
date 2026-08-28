"""Storm severity validator — the RIGHT ruler for a wide, track-based hazard.

Counting how many tracks pass near a point saturates (over decades, nearly every exposed cell has one), which
is why the count test grades storm "not testable". Our storm score is about SEVERITY (how hard it would hit),
so we test it against the observed PEAK intensity of the storms that actually reached each location: among
places storms do hit, does a higher score go with a stronger observed storm? That is a `rank` test on a
continuous target (max wind, kt) — no saturation, no occurrence/AUC.
"""
from __future__ import annotations

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.model_validation import _hav_vec, _load_cells
from services.validation.engine import ValidationResult, register

RADIUS_KM = 25.0


def _peak_intensity_near(cell_lat, cell_lon, ev_lat, ev_lon, ev_int, radius_km):
    """Max observed intensity within each cell's near field (0 where no storm reached it). Binned join."""
    binsize = max(radius_km / 111.0, 1e-6)
    grid: dict = {}
    for i in range(len(ev_lat)):
        grid.setdefault((int(ev_lat[i] // binsize), int(ev_lon[i] // binsize)), []).append(i)
    peak = np.zeros(len(cell_lat))
    for ci in range(len(cell_lat)):
        la, lo = cell_lat[ci], cell_lon[ci]
        bx, by = int(la // binsize), int(lo // binsize)
        cand: list[int] = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cand.extend(grid.get((bx + dx, by + dy), ()))
        if cand:
            idx = np.asarray(cand)
            near = idx[_hav_vec(la, lo, ev_lat[idx], ev_lon[idx]) <= radius_km]
            if len(near):
                peak[ci] = float(ev_int[near].max())
    return peak


def _run(session: Session) -> ValidationResult:
    lat, lon, score, cells = _load_cells(session, "storm")
    rows = session.execute(text(
        "SELECT CAST(lat AS FLOAT), CAST(lon AS FLOAT), CAST(max_wind_kt AS FLOAT) "
        "FROM storm_events WHERE max_wind_kt IS NOT NULL")).all()
    ev_lat = np.array([r[0] for r in rows]); ev_lon = np.array([r[1] for r in rows])
    ev_int = np.array([r[2] for r in rows])
    peak = (_peak_intensity_near(lat, lon, ev_lat, ev_lon, ev_int, RADIUS_KM)
            if len(ev_lat) else np.zeros(len(score)))
    # test only where a storm actually reached (peak>0): "among hit locations, does score track severity?"
    hit = peak > 0
    return ValidationResult(
        hazard_type="storm", kind="rank",
        predicted=score[hit].tolist(), observed=peak[hit].tolist(),
        labels=[c for c, h in zip(cells, hit) if h],
        target_source="NOAA IBTrACS peak wind (max_wind_kt)", scope="global", method="in_sample",
        notes=(f"storm score vs observed peak intensity within ≤{RADIUS_KM:.0f} km, over locations a storm "
               f"actually reached — the severity-appropriate test (near-field COUNT saturates for storms)"),
    )


register("storm")(_run)
