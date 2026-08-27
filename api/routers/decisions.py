"""Forward-risk decisions — the 'Act' surface. One shared endpoint set; the vertical is resolved from the
org's own type, so a bank, asset manager, insurer or REIT each acts on its own book through the same API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import services.intelligence.forward_decisions as D
from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/decisions", tags=["Forward-risk decisions"])


def _vertical(ctx: dict) -> str:
    v = D.VERTICAL.get(ctx["org"].get("type"))
    if not v:
        raise HTTPException(400, {"error": "unsupported", "message": "Forward-risk decisions aren't wired for this sector."})
    return v


@router.get("/actions", summary="The decision verb-pack for this sector")
def actions(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    v = _vertical(ctx)
    return {"vertical": v, "subject_noun": D.SUBJECT_NOUN.get(v, "exposure"),
            "actions": list(D.actions_for(v)), "labels": D.ACTION_LABELS}


class DecideBody(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    scenario: str
    horizon: str
    action: str = Field(..., description="reprice | engage | disclose | monitor | accept")
    rationale: Optional[str] = Field(None, max_length=2000)
    value_eur: Optional[float] = None   # the exposure's value — evaluated against the 4-eyes threshold


@router.get("/crossings", summary="Exposures newly crossing into High+ by a scenario/horizon")
def crossings(session: DbSession, scenario: str = "disorderly_2c", horizon: str = "2050",
              ctx: dict = Depends(require_permission("reports.view"))):
    try:
        rows = D.crossings(session, ctx["org"]["org_id"], _vertical(ctx), scenario, horizon)
    except D.DecisionError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})
    return {"scenario": scenario, "horizon": horizon, "at_risk_threshold": D.AT_RISK,
            "policy": D.decision_policy(session, ctx["org"]["org_id"]),
            "n": len(rows), "crossings": rows}


@router.post("", status_code=201, summary="Record a decision on an exposure")
def decide(body: DecideBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    _vertical(ctx)   # gate to financial orgs
    try:
        return D.decide(session, ctx["org"]["org_id"], ctx["user"]["id"], entity_id=body.entity_id,
                        entity_name=body.entity_name, scenario=body.scenario, horizon=body.horizon,
                        action=body.action, rationale=body.rationale, value_eur=body.value_eur)
    except D.DecisionError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})


@router.get("/log", summary="The decision audit log")
def log(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"decisions": D.decisions_log(session, ctx["org"]["org_id"])}


@router.get("/disclosure-flags", summary="Exposures flagged for the next climate filing")
def disclosure_flags(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"flags": D.disclosure_flags(session, ctx["org"]["org_id"])}


@router.post("/disclosure-flags/{flag_id}/resolve", status_code=204, summary="Mark a disclosure flag included / dismissed")
def resolve_flag(flag_id: str, session: DbSession, status: str = "included",
                 ctx: dict = Depends(require_permission("approvals.create"))):
    from fastapi import Response
    try:
        D.resolve_disclosure_flag(session, ctx["org"]["org_id"], flag_id, ctx["user"]["id"], status)
    except D.DecisionError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})
    return Response(status_code=204)


@router.get("/watchlist", summary="Exposures on the monitor watchlist")
def watchlist(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"watches": D.watchlist(session, ctx["org"]["org_id"])}


@router.post("/watchlist/recheck", summary="Re-score the watchlist now (escalates further deterioration)")
def recheck(session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    escalated = D.recheck_watchlist(session, ctx["org"]["org_id"], due_only=False)
    return {"escalated": escalated, "n": len(escalated)}


@router.post("/watchlist/{watch_id}/resolve", status_code=204, summary="Clear a watch (or mark it escalated)")
def resolve_watch(watch_id: str, session: DbSession, status: str = "cleared",
                  ctx: dict = Depends(require_permission("approvals.create"))):
    from fastapi import Response
    try:
        D.resolve_watch(session, ctx["org"]["org_id"], watch_id, ctx["user"]["id"], status)
    except D.DecisionError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})
    return Response(status_code=204)
