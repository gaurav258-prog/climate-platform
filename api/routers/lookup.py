"""
Public "any address on Earth" hazard lookup — no auth, unlike customer_locations
(which is scoped to a paying customer's registered portfolio). Anyone can check any
address; the platform decides live what it can and can't answer honestly.

Flow: geocode (if an address was given) -> lat/lon -> H3 cell -> check canonical_scores
for every hazard. A cache hit returns instantly. A cache miss is handled per-hazard by
cost:
  - seismic scores synchronously in-request (scripts.score_point_on_demand — the
    global USGS catalog is already ingested, no external fetch needed).
  - flood kicks off a background job (scripts.score_point_gridded_on_demand) since it
    needs a real Copernicus CDS fetch, which this project's own experience shows takes
    2-14 minutes to queue — the response returns 'pending' + a lookup_id immediately;
    poll GET /v1/lookup/score/{lookup_id} until it resolves. FastAPI's built-in
    BackgroundTasks is used deliberately as the SMALLEST viable step: no new
    dependency (already part of the fastapi package this project uses), at the cost
    of no retry/durability if the server restarts mid-job. Celery/SQS+Redis is the
    correct upgrade path if this gets real traffic — not built here, flagged not
    silently assumed away.
  - every other hazard (wildfire/heat/drought/pollution once it exists,
    volcanic/storm outside their backtest regions) still reports 'insufficient_data'
    — each would need its own "compute_for_point" function following flood's shape,
    not yet built.

Every lookup is logged to public_lookups — a lead-gen signal (which addresses do
strangers check) as much as a cache-key/job-tracker, kept separate from paying
customers' data.
"""
from __future__ import annotations

import uuid
from typing import Optional

import h3
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from sqlalchemy import text

from api.deps import DbSession
from api.schemas.lookup import HazardLookupResult, LookupResponse
from core.db.session import get_session
from core.types import HAZARD_VALUES
from services.geocoding.nominatim import geocode
from scripts.score_point_on_demand import score_seismic_point
from scripts.score_point_gridded_on_demand import run_flood_lookup, run_pollution_lookup

router = APIRouter(prefix="/v1/lookup", tags=["Lookup"])

# Hazards scored synchronously, in-request (cheap: no external fetch needed).
SYNC_ON_DEMAND_SCORERS = {"seismic": score_seismic_point}

# Hazards that need a real data fetch, run as a background job (see module docstring).
GRIDDED_ON_DEMAND_SCORERS = {"flood": run_flood_lookup, "pollution": run_pollution_lookup}


@router.get("/score", response_model=LookupResponse, summary="Look up hazard scores for any address or coordinates")
def lookup_score(
    session: DbSession,
    background_tasks: BackgroundTasks,
    address: Optional[str] = Query(default=None, description="Free-text address, geocoded via Nominatim"),
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lon: Optional[float] = Query(default=None, ge=-180, le=180),
):
    display_name = None
    if address:
        geo = geocode(address)
        if not geo:
            raise HTTPException(status_code=404, detail=f"Could not geocode address: {address!r}")
        lat, lon, display_name = geo["lat"], geo["lon"], geo["display_name"]
    elif lat is None or lon is None:
        raise HTTPException(status_code=400, detail="Provide either 'address' or both 'lat' and 'lon'.")

    cell = h3.latlng_to_cell(lat, lon, 8)
    results: list[HazardLookupResult] = []

    for hazard in HAZARD_VALUES:
        cached = session.execute(text("""
            SELECT CAST(risk_score AS FLOAT) risk_score, risk_bucket
            FROM canonical_scores
            WHERE hazard_type=:h AND h3_cell=:c AND scenario='baseline'
              AND time_horizon='current' AND valid_to IS NULL
        """), {"h": hazard, "c": cell}).mappings().first()

        if cached:
            results.append(HazardLookupResult(
                hazard_type=hazard, status="cached_hit",
                risk_score=cached["risk_score"], risk_bucket=cached["risk_bucket"],
            ))
            continue

        sync_scorer = SYNC_ON_DEMAND_SCORERS.get(hazard)
        if sync_scorer:
            outcome = sync_scorer(lat, lon)
            results.append(HazardLookupResult(
                hazard_type=hazard, status=outcome["status"],
                risk_score=outcome.get("risk_score"), risk_bucket=outcome.get("risk_bucket"),
                reason=outcome.get("reason"),
            ))
            continue

        gridded_job = GRIDDED_ON_DEMAND_SCORERS.get(hazard)
        if gridded_job:
            job_id = str(uuid.uuid4())
            # Deliberately NOT using the request-scoped `session` here: FastAPI runs
            # BackgroundTasks BEFORE a Depends(yield) dependency's cleanup commits
            # (see fastapi.routing.request_response — `await response(...)`, which
            # executes background tasks, happens INSIDE the dependency's AsyncExitStack,
            # not after it). If this INSERT rode on `session`, the background job would
            # start querying `public_lookups` for a row that isn't committed yet -- a
            # real bug caught live in this project (rowcount=0 on the job's own UPDATE,
            # confirmed via direct instrumentation, not assumed). A short-lived,
            # immediately-committing session guarantees the row exists before the
            # background task can possibly run.
            with get_session() as immediate:
                immediate.execute(text("""
                    INSERT INTO public_lookups (lookup_id, raw_address, latitude, longitude, h3_cell_r8, status)
                    VALUES (:id, :addr, :lat, :lon, :cell, 'computing')
                """), {"id": job_id, "addr": address, "lat": lat, "lon": lon, "cell": cell})
            background_tasks.add_task(gridded_job, job_id, lat, lon)
            results.append(HazardLookupResult(hazard_type=hazard, status="pending", lookup_id=job_id))
            continue

        results.append(HazardLookupResult(
            hazard_type=hazard, status="insufficient_data",
            reason="on-demand scoring for this hazard isn't available yet outside pre-scored regions",
        ))

    session.execute(text("""
        INSERT INTO public_lookups (lookup_id, raw_address, latitude, longitude, h3_cell_r8, status, completed_at)
        VALUES (:id, :addr, :lat, :lon, :cell, 'done', now())
    """), {"id": str(uuid.uuid4()), "addr": address, "lat": lat, "lon": lon, "cell": cell})

    return LookupResponse(latitude=lat, longitude=lon, display_name=display_name, h3_cell=cell, hazards=results)


@router.get(
    "/score/{lookup_id}",
    response_model=HazardLookupResult,
    summary="Poll a pending gridded-hazard lookup for its result",
)
def poll_lookup(lookup_id: str, session: DbSession):
    job = session.execute(text("""
        SELECT status, h3_cell_r8 FROM public_lookups WHERE lookup_id=:id
    """), {"id": lookup_id}).mappings().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"No lookup job {lookup_id!r}")

    if job["status"] == "computing":
        return HazardLookupResult(hazard_type="unknown", status="pending", lookup_id=lookup_id)

    if job["status"] == "failed":
        return HazardLookupResult(hazard_type="unknown", status="failed",
                                   reason="the background fetch/scoring job failed", lookup_id=lookup_id)

    # status == 'done' — find whichever hazard just got written for this cell
    score = session.execute(text("""
        SELECT hazard_type, CAST(risk_score AS FLOAT) risk_score, risk_bucket
        FROM canonical_scores
        WHERE h3_cell=:c AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
        ORDER BY scored_at DESC LIMIT 1
    """), {"c": job["h3_cell_r8"]}).mappings().first()
    if not score:
        return HazardLookupResult(hazard_type="unknown", status="failed",
                                   reason="job finished but no score was written", lookup_id=lookup_id)

    return HazardLookupResult(
        hazard_type=score["hazard_type"], status="done",
        risk_score=score["risk_score"], risk_bucket=score["risk_bucket"], lookup_id=lookup_id,
    )
