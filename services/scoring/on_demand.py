"""
Shared hazard-scorer wiring for "score this H3 cell if it isn't already scored" --
factored out of api/routers/lookup.py (the any-address feature) so it can also be
called from the vertical upload endpoints (bank/supply/insurance): an uploaded
asset landing in an unscored cell should get the exact same treatment an
address-lookup query does, not a second, drifting copy of this wiring.
"""
from __future__ import annotations

import logging
import threading

from ml.features.heat_chronic_point import score_heat_chronic_point
from ml.scoring.climate_change_point import (
    score_changing_precip_point,
    score_changing_temp_point,
    score_changing_wind_point,
)
from ml.scoring.climate_variability_point import score_precip_variability_point, score_temp_variability_point
from ml.scoring.coastal_flood_point import score_coastal_flood_point
from ml.scoring.frost_point import score_frost_point
from ml.scoring.heavy_precip_point import score_heavy_precip_point
from ml.scoring.coastal_erosion_point import score_coastal_erosion_point
from ml.scoring.landslide_point import score_landslide_point
from ml.scoring.permafrost_point import score_permafrost_point
from ml.scoring.soil_erosion_point import score_soil_erosion_point
from ml.scoring.subsidence_point import score_subsidence_point
from ml.scoring.water_stress_point import score_water_stress_point
from scripts.score_point_on_demand import score_seismic_point, score_storm_point
from services.tasks.hazard_tasks import HAZARD_TASKS

# Hazards scored synchronously, in-request (cheap: read a global baseline, no external fetch).
# soil_water + frost were globally scored by batch jobs but were absent here, so a NEWLY-uploaded
# plot/asset never got them — only the other 8 hazards. Both point scorers read their global baseline
# (soil_moisture_baseline / frost_baseline) and self-cache, so an arbitrary address now gets the full
# water + frost picture on demand, exactly like the any-address lookup.
SYNC_ON_DEMAND_SCORERS = {
    "seismic": score_seismic_point, "heat_chronic": score_heat_chronic_point,
    "storm": score_storm_point,
    "soil_water": score_water_stress_point, "frost": score_frost_point,
    "coastal_flood": score_coastal_flood_point,
    "heavy_precip": score_heavy_precip_point,
    "landslide": score_landslide_point,
    "temp_variability": score_temp_variability_point,
    "precip_variability": score_precip_variability_point,
    # projection-based change channels — real under a projection scenario, insufficient at baseline/current
    "changing_temp": score_changing_temp_point,
    "changing_precip": score_changing_precip_point,
    "changing_wind": score_changing_wind_point,
    # EU-Taxonomy solid-mass / erosion channels (subsidence + coastal_erosion live; permafrost + soil_erosion
    # return insufficient_data until their raster is fetched — wired-ready, no code change on drop-in)
    "subsidence": score_subsidence_point,
    "coastal_erosion": score_coastal_erosion_point,
    "permafrost": score_permafrost_point,
    "soil_erosion": score_soil_erosion_point,
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


logger = logging.getLogger(__name__)


def schedule_scoring(cell_coords: dict) -> None:
    """Fire-and-forget version of process_new_cells for the write path.

    Scoring a brand-new cell means synchronous ERA5/raster reads (~seconds), which would
    otherwise block the add/edit/upload request. process_new_cells opens its OWN DB sessions
    (get_session), so running it in a daemon thread here is safe — the request returns
    immediately and the score lands a moment later. Already-scored cells are a fast no-op.
    """
    if not cell_coords:
        return

    def _run() -> None:
        try:
            process_new_cells(cell_coords)
        except Exception:
            logger.warning("background scoring failed for cells %s", list(cell_coords), exc_info=True)

    threading.Thread(target=_run, name="score-cells", daemon=True).start()


def warm_sync_scores(cell_coords: dict, scenario: str = "baseline", horizon: str = "current") -> None:
    """Score ONLY the fetch-free hazards (seismic/heat_chronic/storm) for a set of cells, in a daemon
    thread. Used by the H3 granular-grid drill-down to fill in the risk texture around a site without a
    Celery broker: each scorer opens its own session, caches its result in canonical_scores, and is a
    fast no-op once a cell is scored. Deliberately does NOT dispatch the gridded (ERA5/raster) hazards —
    those still need the async worker, so a cell shows real seismic/heat/storm here and stays honestly
    grey for the gridded hazards until the worker runs.
    """
    if not cell_coords:
        return

    def _score_cell(lat: float, lon: float) -> None:
        for hazard, scorer in SYNC_ON_DEMAND_SCORERS.items():
            try:
                scorer(lat, lon, scenario=scenario, horizon=horizon) if hazard == "heat_chronic" else scorer(lat, lon)
            except TypeError:
                try:
                    scorer(lat, lon)
                except Exception:
                    pass
            except Exception:
                pass  # one hazard on one cell must never abort the rest of the ring

    def _run() -> None:
        # The scorers are I/O-bound (baseline reads), so score cells concurrently — a 19-cell ring fills
        # in a few seconds instead of ~a minute. Capped low to stay well under the DB connection pool.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=5, thread_name_prefix="warm-ring") as ex:
            for lat, lon in cell_coords.values():
                ex.submit(_score_cell, lat, lon)

    threading.Thread(target=_run, name="warm-ring-sync", daemon=True).start()
