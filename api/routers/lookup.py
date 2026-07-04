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
  - pollution/wildfire/heat_acute/drought follow the same gridded-job path as flood
    (scripts.score_point_gridded_on_demand / score_heat_on_demand / score_drought_on_demand).
  - heat_chronic and volcanic/storm outside their curated backtest regions still
    report 'insufficient_data' — heat_chronic has no methodology defined anywhere in
    this project yet (not just "not wired here"); volcanic/storm need a live global
    event catalog, not just a point-scoring function, to go beyond their backtest
    regions — genuinely bigger lifts, not oversights.

The response also carries `overall` (OverallRisk) — the actual "ONE easy number" the
platform's own pitch promises, computed as the MAX across every hazard scored for this
cell right now (see OverallRisk's docstring for why max, not average). `status=
'provisional'` when hazards are still computing in the background — re-poll or re-call
this endpoint to refine as more of them resolve.

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
from api.schemas.lookup import HazardLookupResult, LookupResponse, OverallRisk, PollResponse
from core.db.session import get_session
from core.types import HAZARD_VALUES, score_to_bucket
from services.geocoding.nominatim import geocode
from scripts.score_point_on_demand import score_seismic_point
from scripts.score_point_gridded_on_demand import run_flood_lookup, run_pollution_lookup, run_wildfire_lookup
from scripts.score_heat_on_demand import run_heat_lookup
from scripts.score_drought_on_demand import run_drought_lookup

router = APIRouter(prefix="/v1/lookup", tags=["Lookup"])

# Hazards scored synchronously, in-request (cheap: no external fetch needed).
SYNC_ON_DEMAND_SCORERS = {"seismic": score_seismic_point}

# Hazards that need a real data fetch, run as a background job (see module docstring).
GRIDDED_ON_DEMAND_SCORERS = {
    "flood": run_flood_lookup, "pollution": run_pollution_lookup, "wildfire": run_wildfire_lookup,
    "heat_acute": run_heat_lookup, "drought": run_drought_lookup,
}


def _compute_overall(session, cell: str) -> OverallRisk:
    """MAX across every hazard scored for this cell right now (see OverallRisk's
    docstring for why max, not average). Re-queries canonical_scores directly rather
    than trusting the caller's in-memory `results` list, so it stays correct when
    called later from poll_lookup() after a background job has since resolved.

    hazards_pending/insufficient are each a DIRECT count of distinct hazard_types,
    not derived by subtraction — lookup_score() doesn't check for an already-in-
    flight job before starting a new one, so repeated calls for the same uncached
    address can leave multiple 'computing' rows for the SAME hazard; a raw COUNT(*)
    (or a 9-minus-scored-minus-pending subtraction) would silently over/under-count
    in that case. A real bug caught live, not a hypothetical."""
    scored = session.execute(text("""
        SELECT hazard_type, CAST(risk_score AS FLOAT) risk_score
        FROM canonical_scores
        WHERE h3_cell=:c AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
    """), {"c": cell}).mappings().all()
    scored_types = {r["hazard_type"] for r in scored}

    pending_types = {row[0] for row in session.execute(text("""
        SELECT DISTINCT hazard_type FROM public_lookups
        WHERE h3_cell_r8=:c AND status='computing' AND hazard_type IS NOT NULL
    """), {"c": cell}).all()}
    pending_types -= scored_types  # a hazard that resolved since its job was marked computing

    if scored:
        driver = max(scored, key=lambda r: r["risk_score"])
        overall_score, overall_bucket = round(driver["risk_score"], 2), score_to_bucket(driver["risk_score"]).value
        driver_hazard = driver["hazard_type"]
    else:
        overall_score = overall_bucket = driver_hazard = None

    n_insufficient = len(set(HAZARD_VALUES) - scored_types - pending_types)
    return OverallRisk(
        score=overall_score, bucket=overall_bucket, driver_hazard=driver_hazard,
        status="provisional" if pending_types else "complete",
        hazards_scored=len(scored_types), hazards_pending=len(pending_types),
        hazards_insufficient=n_insufficient,
    )


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
                    INSERT INTO public_lookups (lookup_id, raw_address, latitude, longitude, h3_cell_r8, hazard_type, status)
                    VALUES (:id, :addr, :lat, :lon, :cell, :hazard, 'computing')
                """), {"id": job_id, "addr": address, "lat": lat, "lon": lon, "cell": cell, "hazard": hazard})
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

    overall = _compute_overall(session, cell)
    return LookupResponse(latitude=lat, longitude=lon, display_name=display_name, h3_cell=cell,
                           hazards=results, overall=overall)


@router.get(
    "/score/{lookup_id}",
    response_model=PollResponse,
    summary="Poll a pending gridded-hazard lookup for its result",
)
def poll_lookup(lookup_id: str, session: DbSession):
    job = session.execute(text("""
        SELECT status, h3_cell_r8 FROM public_lookups WHERE lookup_id=:id
    """), {"id": lookup_id}).mappings().first()
    if not job:
        raise HTTPException(status_code=404, detail=f"No lookup job {lookup_id!r}")

    cell = job["h3_cell_r8"]

    if job["status"] == "computing":
        hazard = HazardLookupResult(hazard_type="unknown", status="pending", lookup_id=lookup_id)
        return PollResponse(hazard=hazard, overall=_compute_overall(session, cell))

    if job["status"] == "failed":
        hazard = HazardLookupResult(hazard_type="unknown", status="failed",
                                     reason="the background fetch/scoring job failed", lookup_id=lookup_id)
        return PollResponse(hazard=hazard, overall=_compute_overall(session, cell))

    # status == 'done' — find whichever hazard just got written for this cell
    score = session.execute(text("""
        SELECT hazard_type, CAST(risk_score AS FLOAT) risk_score, risk_bucket
        FROM canonical_scores
        WHERE h3_cell=:c AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
        ORDER BY scored_at DESC LIMIT 1
    """), {"c": cell}).mappings().first()
    if not score:
        hazard = HazardLookupResult(hazard_type="unknown", status="failed",
                                     reason="job finished but no score was written", lookup_id=lookup_id)
        return PollResponse(hazard=hazard, overall=_compute_overall(session, cell))

    hazard = HazardLookupResult(
        hazard_type=score["hazard_type"], status="done",
        risk_score=score["risk_score"], risk_bucket=score["risk_bucket"], lookup_id=lookup_id,
    )
    return PollResponse(hazard=hazard, overall=_compute_overall(session, cell))
