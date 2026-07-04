"""
Shared hazard-scorer wiring for "score this H3 cell if it isn't already scored" --
factored out of api/routers/lookup.py (the any-address feature) so it can also be
called from the vertical upload endpoints (bank/supply/insurance): an uploaded
asset landing in an unscored cell should get the exact same treatment an
address-lookup query does, not a second, drifting copy of this wiring.
"""
from __future__ import annotations

from services.tasks.hazard_tasks import HAZARD_TASKS
from scripts.score_point_on_demand import score_seismic_point, score_storm_point
from ml.features.heat_chronic_point import score_heat_chronic_point

# Hazards scored synchronously, in-request (cheap: no external fetch needed).
SYNC_ON_DEMAND_SCORERS = {
    "seismic": score_seismic_point, "heat_chronic": score_heat_chronic_point,
    "storm": score_storm_point,
}

# Hazards that need a real data fetch, run as a Celery job (see services/tasks/).
GRIDDED_ON_DEMAND_SCORERS = HAZARD_TASKS


def process_new_cells(cell_coords: dict) -> dict:
    """cell_coords: {h3_cell: (lat, lon)}. For each (cell, hazard) pair not already
    in canonical_scores, dispatch scoring -- sync hazards score immediately
    in-request, gridded ones are queued as Celery jobs (fire-and-forget, same
    'computing' row shape api/routers/lookup.py already uses for a single-address
    lookup). Returns counts, not full per-hazard results -- an upload can span
    many rows/cells at once, unlike a single lookup.
    """
    import uuid
    from sqlalchemy import text
    from core.db.session import get_session

    cells = list(cell_coords.keys())
    if not cells:
        return {"n_cells": 0, "n_sync_scored": 0, "n_gridded_dispatched": 0}

    with get_session() as s:
        existing = s.execute(text("""
            SELECT DISTINCT h3_cell, hazard_type FROM canonical_scores
            WHERE h3_cell = ANY(:cells) AND valid_to IS NULL
        """), {"cells": cells}).all()
    existing_pairs = {(row[0], row[1]) for row in existing}

    n_sync, n_gridded = 0, 0
    for cell, (lat, lon) in cell_coords.items():
        for hazard, scorer in SYNC_ON_DEMAND_SCORERS.items():
            if (cell, hazard) in existing_pairs:
                continue
            try:
                scorer(lat, lon)
                n_sync += 1
            except Exception:
                pass  # a single hazard's on-demand scorer failing shouldn't fail the whole upload
        for hazard, job in GRIDDED_ON_DEMAND_SCORERS.items():
            if (cell, hazard) in existing_pairs:
                continue
            job_id = str(uuid.uuid4())
            with get_session() as immediate:
                immediate.execute(text("""
                    INSERT INTO public_lookups (lookup_id, latitude, longitude, h3_cell_r8, hazard_type, status)
                    VALUES (:id, :lat, :lon, :cell, :hazard, 'computing')
                """), {"id": job_id, "lat": lat, "lon": lon, "cell": cell, "hazard": hazard})
            job.delay(job_id, lat, lon)
            n_gridded += 1

    return {"n_cells": len(cells), "n_sync_scored": n_sync, "n_gridded_dispatched": n_gridded}
