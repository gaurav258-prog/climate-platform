"""
Score query endpoints — read-only views into canonical_scores.

All endpoints query canonical_scores WHERE valid_to IS NULL
(current scores only). Historical score chains are available via
the /scores/{h3_cell}/history endpoint.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from api.deps import CustomerId, DbSession, Pagination
from api.schemas.scores import ScoreListResponse, ScoreResponse, VelocityAlert

router = APIRouter(prefix="/v1/scores", tags=["Scores"])

# Velocity threshold above which we surface an alert in the response header
VELOCITY_ALERT_THRESHOLD = 10.0   # score points / period


def _row_to_score(row: dict) -> ScoreResponse:
    return ScoreResponse(
        h3_cell=row["h3_cell"],
        h3_resolution=row["h3_resolution"] or 8,
        hazard_type=row["hazard_type"],
        scenario=row["scenario"],
        time_horizon=row["time_horizon"],
        risk_score=float(row["risk_score"]),
        risk_bucket=row["risk_bucket"],
        score_ci_lower=float(row["ci_lower"])  if row.get("ci_lower")  is not None else None,
        score_ci_upper=float(row["ci_upper"])  if row.get("ci_upper")  is not None else None,
        score_velocity_6h=float(row["v6h"])    if row.get("v6h")       is not None else None,
        score_velocity_24h=float(row["v24h"])  if row.get("v24h")      is not None else None,
        score_velocity_48h=float(row["v48h"])  if row.get("v48h")      is not None else None,
        ensemble_scores=row.get("ensemble_scores"),
        compound_flag=row.get("compound_flag"),
        regulatory_fingerprint=row.get("regulatory_fingerprint"),
        model_version=row["model_version"],
        scored_at=row["scored_at"],
        valid_from=row["valid_from"],
    )


# ── GET /v1/scores/cell/{h3_cell} ─────────────────────────────────────

@router.get(
    "/cell/{h3_cell}",
    response_model=ScoreListResponse,
    summary="Get current scores for an H3 cell",
    description=(
        "Returns the latest canonical score(s) for a given H3 cell across all hazard types "
        "and scenarios. Filter by hazard_type and/or scenario to narrow results."
    ),
)
def get_cell_scores(
    h3_cell:     str,
    session:     DbSession,
    hazard_type: Optional[str] = Query(default=None, description="flood | wildfire | heat_acute"),
    scenario:    Optional[str] = Query(default="baseline"),
    horizon:     Optional[str] = Query(default="current"),
):
    filters = ["h3_cell = :h3_cell", "valid_to IS NULL"]
    params: dict = {"h3_cell": h3_cell}

    if hazard_type:
        filters.append("hazard_type = :hazard_type")
        params["hazard_type"] = hazard_type
    if scenario:
        filters.append("scenario = :scenario")
        params["scenario"] = scenario
    if horizon:
        filters.append("time_horizon = :horizon")
        params["horizon"] = horizon

    rows = session.execute(text(f"""
        SELECT h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
               CAST(risk_score AS FLOAT)         AS risk_score,
               risk_bucket, model_version, scored_at, valid_from,
               CAST(score_ci_lower  AS FLOAT)    AS ci_lower,
               CAST(score_ci_upper  AS FLOAT)    AS ci_upper,
               CAST(score_velocity_6h  AS FLOAT) AS v6h,
               CAST(score_velocity_24h AS FLOAT) AS v24h,
               CAST(score_velocity_48h AS FLOAT) AS v48h,
               ensemble_scores, compound_flag, regulatory_fingerprint
        FROM   canonical_scores
        WHERE  {" AND ".join(filters)}
        ORDER  BY hazard_type, scenario
    """), params).mappings().all()

    scores = [_row_to_score(dict(r)) for r in rows]
    return ScoreListResponse(total=len(scores), scores=scores)


# ── GET /v1/scores/cell/{h3_cell}/history ─────────────────────────────

@router.get(
    "/cell/{h3_cell}/history",
    response_model=ScoreListResponse,
    summary="Full score history for an H3 cell",
    description="Returns all historical scores (including retired ones) for audit and trend analysis.",
)
def get_cell_history(
    h3_cell:     str,
    session:     DbSession,
    hazard_type: str   = Query(...,       description="flood | wildfire | heat_acute"),
    scenario:    str   = Query("baseline"),
    pagination:  Pagination = None,
):
    rows = session.execute(text("""
        SELECT h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
               CAST(risk_score AS FLOAT)         AS risk_score,
               risk_bucket, model_version, scored_at, valid_from,
               CAST(score_ci_lower  AS FLOAT)    AS ci_lower,
               CAST(score_ci_upper  AS FLOAT)    AS ci_upper,
               CAST(score_velocity_6h  AS FLOAT) AS v6h,
               CAST(score_velocity_24h AS FLOAT) AS v24h,
               CAST(score_velocity_48h AS FLOAT) AS v48h,
               ensemble_scores, compound_flag, regulatory_fingerprint
        FROM   canonical_scores
        WHERE  h3_cell     = :h3_cell
        AND    hazard_type = :hazard
        AND    scenario    = :scenario
        ORDER  BY scored_at DESC
        LIMIT  :limit OFFSET :offset
    """), {
        "h3_cell": h3_cell, "hazard": hazard_type, "scenario": scenario,
        "limit":  (pagination or {}).get("limit", 100),
        "offset": (pagination or {}).get("offset", 0),
    }).mappings().all()

    scores = [_row_to_score(dict(r)) for r in rows]
    return ScoreListResponse(total=len(scores), scores=scores)


# ── GET /v1/scores/portfolio ──────────────────────────────────────────

@router.get(
    "/portfolio",
    response_model=ScoreListResponse,
    summary="Current scores for all customer locations",
    description=(
        "Returns the latest canonical score for every registered location in the customer's "
        "portfolio. Joins customer_locations → canonical_scores on h3_cell."
    ),
)
def get_portfolio_scores(
    session:     DbSession,
    customer_id: CustomerId,
    hazard_type: Optional[str] = Query(default=None),
    scenario:    str = Query(default="baseline"),
    horizon:     str = Query(default="current"),
    min_score:   Optional[float] = Query(default=None, ge=0, le=100,
                                         description="Filter: only return scores ≥ this value"),
):
    filters = [
        "cl.customer_id = :customer_id",
        "cl.is_active   = true",
        "cs.scenario    = :scenario",
        "cs.time_horizon = :horizon",
        "cs.valid_to    IS NULL",
    ]
    params: dict = {
        "customer_id": customer_id,
        "scenario":    scenario,
        "horizon":     horizon,
    }

    if hazard_type:
        filters.append("cs.hazard_type = :hazard_type")
        params["hazard_type"] = hazard_type
    if min_score is not None:
        filters.append("CAST(cs.risk_score AS FLOAT) >= :min_score")
        params["min_score"] = min_score

    rows = session.execute(text(f"""
        SELECT DISTINCT ON (cl.location_id, cs.hazard_type)
               cs.h3_cell, cs.h3_resolution, cs.hazard_type, cs.scenario,
               cs.time_horizon,
               CAST(cs.risk_score AS FLOAT)         AS risk_score,
               cs.risk_bucket, cs.model_version, cs.scored_at, cs.valid_from,
               CAST(cs.score_ci_lower  AS FLOAT)    AS ci_lower,
               CAST(cs.score_ci_upper  AS FLOAT)    AS ci_upper,
               CAST(cs.score_velocity_6h  AS FLOAT) AS v6h,
               CAST(cs.score_velocity_24h AS FLOAT) AS v24h,
               CAST(cs.score_velocity_48h AS FLOAT) AS v48h,
               cs.ensemble_scores, cs.compound_flag, cs.regulatory_fingerprint
        FROM   customer_locations cl
        JOIN   canonical_scores   cs ON cs.h3_cell = cl.h3_cell_r8
        WHERE  {" AND ".join(filters)}
        ORDER  BY cl.location_id, cs.hazard_type, cs.scored_at DESC
    """), params).mappings().all()

    scores = [_row_to_score(dict(r)) for r in rows]
    return ScoreListResponse(total=len(scores), scores=scores)


# ── GET /v1/scores/portfolio/alerts ───────────────────────────────────

@router.get(
    "/portfolio/alerts",
    response_model=list[VelocityAlert],
    summary="Rapidly rising scores in portfolio",
    description=(
        "Returns cells where 24h score velocity exceeds the alert threshold "
        f"(default ±{VELOCITY_ALERT_THRESHOLD} points). Use to surface emerging risks."
    ),
)
def get_velocity_alerts(
    session:     DbSession,
    customer_id: CustomerId,
    threshold:   float = Query(default=VELOCITY_ALERT_THRESHOLD, ge=1, le=50),
):
    rows = session.execute(text("""
        SELECT DISTINCT ON (cl.location_id, cs.hazard_type)
               cs.h3_cell, cs.hazard_type,
               CAST(cs.score_velocity_24h AS FLOAT) AS v24h,
               CAST(cs.risk_score         AS FLOAT) AS risk_score,
               cs.risk_bucket
        FROM   customer_locations cl
        JOIN   canonical_scores   cs ON cs.h3_cell = cl.h3_cell_r8
        WHERE  cl.customer_id       = :customer_id
        AND    cl.is_active         = true
        AND    cs.valid_to          IS NULL
        AND    ABS(CAST(cs.score_velocity_24h AS FLOAT)) >= :threshold
        ORDER  BY cl.location_id, cs.hazard_type, cs.scored_at DESC
    """), {"customer_id": customer_id, "threshold": threshold}).mappings().all()

    return [
        VelocityAlert(
            h3_cell=r["h3_cell"],
            hazard_type=r["hazard_type"],
            velocity_24h=r["v24h"],
            current_score=r["risk_score"],
            risk_bucket=r["risk_bucket"],
            alert_reason=(
                f"Score {'rose' if r['v24h'] > 0 else 'fell'} "
                f"{abs(r['v24h']):.1f} pts in 24h"
            ),
        )
        for r in rows
    ]


# ── GET /v1/scores/compound ───────────────────────────────────────────

@router.get(
    "/compound",
    summary="Active compound events in portfolio",
    description="Cells where 2+ hazards are simultaneously elevated (≥60) for 3+ days.",
)
def get_compound_events(
    session:     DbSession,
    customer_id: CustomerId,
):
    from ml.scoring.compound import summarise_compound_events
    from datetime import date

    events = summarise_compound_events(session, date.today())

    # Filter to customer's cells
    customer_cells = session.execute(text("""
        SELECT h3_cell_r8 FROM customer_locations
        WHERE  customer_id = :cid AND is_active = true
    """), {"cid": customer_id}).scalars().all()

    cell_set = set(customer_cells)
    return [e for e in events if e["h3_cell"] in cell_set]
