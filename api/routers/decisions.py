"""Forward-risk decisions — the 'Act' surface. One shared endpoint set; the vertical is resolved from the
org's own type, so a bank, asset manager, insurer or REIT each acts on its own book through the same API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
import services.intelligence.forward_decisions as D

router = APIRouter(prefix="/v1/decisions", tags=["Forward-risk decisions"])


def _vertical(ctx: dict) -> str:
    v = D.VERTICAL.get(ctx["org"].get("type"))
    if not v:
        raise HTTPException(400, {"error": "unsupported", "message": "Forward-risk decisions are for financial books only."})
    return v


class DecideBody(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    scenario: str
    horizon: str
    action: str = Field(..., description="reprice | engage | disclose | monitor | accept")
    rationale: Optional[str] = Field(None, max_length=2000)


@router.get("/crossings", summary="Exposures newly crossing into High+ by a scenario/horizon")
def crossings(session: DbSession, scenario: str = "disorderly_2c", horizon: str = "2050",
              ctx: dict = Depends(require_permission("reports.view"))):
    try:
        rows = D.crossings(session, ctx["org"]["org_id"], _vertical(ctx), scenario, horizon)
    except D.DecisionError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})
    return {"scenario": scenario, "horizon": horizon, "at_risk_threshold": D.AT_RISK,
            "n": len(rows), "crossings": rows}


@router.post("", status_code=201, summary="Record a decision on an exposure")
def decide(body: DecideBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    _vertical(ctx)   # gate to financial orgs
    try:
        return D.decide(session, ctx["org"]["org_id"], ctx["user"]["id"], entity_id=body.entity_id,
                        entity_name=body.entity_name, scenario=body.scenario, horizon=body.horizon,
                        action=body.action, rationale=body.rationale)
    except D.DecisionError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})


@router.get("/log", summary="The decision audit log")
def log(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"decisions": D.decisions_log(session, ctx["org"]["org_id"])}
