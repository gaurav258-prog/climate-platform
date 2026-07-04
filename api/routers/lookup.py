"""
Public "any address on Earth" hazard lookup — no auth, unlike customer_locations
(which is scoped to a paying customer's registered portfolio). Anyone can check any
address; the platform decides live what it can and can't answer honestly.

Flow: geocode (if an address was given) -> lat/lon -> H3 cell -> check canonical_scores
for every hazard. A cache hit returns instantly. A cache miss is handled per-hazard by
cost:
  - seismic scores synchronously in-request (scripts.score_point_on_demand — the
    global USGS catalog is already ingested, no external fetch needed).
  - heat_chronic ALSO scores synchronously (ml.features.heat_chronic_point) — unlike
    heat_acute, it's a pure function of the 30-year climatology_baseline table already
    built, no live CDS fetch needed, so it's the same cost tier as seismic, not a
    background job. Methodology: expected days/year where mean temperature exceeds
    the C3S "Hot Days" 30C reference (disclosed as a mean-temp proxy for C3S's own
    max-temp definition — see ml/scoring/heat_chronic.py).
  - flood kicks off a Celery job (services.tasks.hazard_tasks) since it needs a real
    Copernicus CDS fetch, which this project's own experience shows takes 2-14 minutes
    to queue — the response returns 'pending' + a lookup_id immediately; poll GET
    /v1/lookup/score/{lookup_id} until it resolves. Originally built on FastAPI's
    in-process BackgroundTasks (the smallest viable step, no new dependency) —
    migrated to Celery+Redis for durability: a job now survives an API server
    restart (a separate worker process executes it, Redis persists the queue), which
    BackgroundTasks genuinely could not do. This does NOT make the external CDS/ADS/
    FIRMS queue times themselves any faster — that latency is the other side's, not
    ours to optimize away. Run the worker separately:
        .venv/bin/celery -A services.tasks.celery_app worker --loglevel=info
  - pollution/wildfire/heat_acute/drought follow the same Celery job path as flood
    (scripts.score_point_gridded_on_demand / score_heat_on_demand / score_drought_on_demand,
    wrapped as tasks in services.tasks.hazard_tasks).
  - storm ALSO scores synchronously (scripts.score_point_on_demand.score_storm_point) —
    reuses the EXISTING Modified Rankine Vortex physics (ml/scoring/storm_physics.py),
    which already generalizes to any storm without per-storm hand-curation. Needed a
    real global IBTrACS ingestion first (scripts/ingest_ibtracs_global.py — all 6
    ocean basins, last 10 years, tropical-storm-strength and up, 966 storms/35,846
    track points), replacing the single-storm Hurricane Maria backtest data that used
    to be all that existed in storm_events.
  - volcanic outside its curated backtest regions still reports 'insufficient_data' —
    unlike storm, its hazard zones (proximal/ashfall radii) are hand-curated per-volcano
    from published papers with no generic fallback formula decided yet, a genuinely
    harder problem than storm's fully-physics-based generalization.

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
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from api.deps import DbSession
from api.schemas.lookup import HazardLookupResult, LookupResponse, OverallRisk, PollResponse
from core.db.session import get_session
from core.types import HAZARD_VALUES, score_to_bucket
from services.geocoding.nominatim import geocode
from services.tasks.hazard_tasks import HAZARD_TASKS
from scripts.score_point_on_demand import score_seismic_point, score_storm_point
from ml.features.heat_chronic_point import score_heat_chronic_point

router = APIRouter(prefix="/v1/lookup", tags=["Lookup"])

# Hazards scored synchronously, in-request (cheap: no external fetch needed).
SYNC_ON_DEMAND_SCORERS = {
    "seismic": score_seismic_point, "heat_chronic": score_heat_chronic_point,
    "storm": score_storm_point,
}

# Hazards that need a real data fetch, run as a Celery job (see module docstring).
GRIDDED_ON_DEMAND_SCORERS = HAZARD_TASKS


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
            # Immediately-committing session, not the request-scoped one: the Celery
            # worker is a SEPARATE PROCESS that could start executing this job before
            # our own request's transaction commits (the same class of visibility bug
            # BackgroundTasks hit here previously — a real, live-confirmed race, not
            # a hypothetical). Guarantee the row exists before the job can run.
            with get_session() as immediate:
                immediate.execute(text("""
                    INSERT INTO public_lookups (lookup_id, raw_address, latitude, longitude, h3_cell_r8, hazard_type, status)
                    VALUES (:id, :addr, :lat, :lon, :cell, :hazard, 'computing')
                """), {"id": job_id, "addr": address, "lat": lat, "lon": lon, "cell": cell, "hazard": hazard})
            gridded_job.delay(job_id, lat, lon)
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
