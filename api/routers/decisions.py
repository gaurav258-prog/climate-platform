"""Risk decisions — the 'Act' surface. One shared endpoint set; the vertical is resolved from the org's own type, so a
bank, asset manager, insurer or REIT each acts on its own book through the same API. Two signals raise what to decide
on: an exposure crossing the stated at-risk level by a pathway (/crossings), and an asset whose tested yearly loss
reaches the stated share of its value (/loss-signals)."""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import services.intelligence.decision_watch as W
import services.intelligence.forward_decisions as D
from api.deps import DbSession, require_permission
from core.errors import UserError

router = APIRouter(prefix="/v1/decisions", tags=["Forward-risk decisions"])


def _vertical(ctx: dict) -> str:
    v = D.VERTICAL.get(ctx["org"].get("type"))
    if not v:
        raise UserError("oversight.decisions.unsupported")
    return v


@router.get("/actions", summary="The decision verb-pack for this sector")
def actions(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    v = _vertical(ctx)
    return {"vertical": v, "subject_noun": D.SUBJECT_NOUN.get(v, "exposure"),
            "actions": list(D.actions_for(v)), "labels": D.ACTION_LABELS}


class DecideBody(BaseModel):
    entity_id: str
    entity_name: Optional[str] = None
    signal: Literal["crossing", "loss"] = "crossing"
    scenario: Optional[str] = Field(None, description="a crossing's pathway; a loss signal is today's climate")
    horizon: Optional[str] = None
    action: str = Field(..., description="reprice | engage | disclose | monitor | accept")
    rationale: Optional[str] = Field(None, max_length=2000)
    value_eur: Optional[float] = None   # the exposure's value — evaluated against the 4-eyes threshold


@router.get("/crossings", summary="Exposures newly crossing the stated at-risk level by a scenario/horizon")
def crossings(session: DbSession, scenario: str = "disorderly_2c", horizon: str = "2050",
              ctx: dict = Depends(require_permission("reports.view"))):
    from services.money.params import for_org
    method = for_org(session, ctx["org"]["org_id"])
    level = method.get("method.at_risk_level")
    if level is None:                    # 'crossing' is the institution's own line — not stated, no crossings (a named gap)
        return {"scenario": scenario, "horizon": horizon, "at_risk_threshold": None, "gap": method.gap_text(),
                "policy": D.decision_policy(session, ctx["org"]["org_id"]), "n": 0, "crossings": []}
    try:
        rows = D.crossings(session, ctx["org"]["org_id"], _vertical(ctx), scenario, horizon, level)
    except D.DecisionError as e:          # the only refusal here: a horizon the projection does not cross by
        raise UserError("oversight.decisions.bad_horizon") from e
    return {"scenario": scenario, "horizon": horizon, "at_risk_threshold": level,
            "policy": D.decision_policy(session, ctx["org"]["org_id"]),
            "n": len(rows), "crossings": rows}


@router.get("/loss-signals", summary="Assets whose tested yearly loss reaches the stated share of their value")
def loss_signals(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from core import messages
    from services.money.params import for_org
    _vertical(ctx)
    out = D.loss_signals(session, ctx["org"]["org_id"], for_org(session, ctx["org"]["org_id"]))
    for sig in out["signals"]:
        for f in sig["figures"]:
            f["peril_name"] = messages.name("peril", f["peril"])
    return {**out, "notice": messages.render(out["why"]) if out["why"] else None,
            "policy": D.decision_policy(session, ctx["org"]["org_id"]), "n": len(out["signals"])}


@router.post("", status_code=201, summary="Record a decision on an exposure")
def decide(body: DecideBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    _vertical(ctx)   # gate to financial orgs
    if body.signal == "crossing" and not (body.scenario and body.horizon):
        raise UserError("oversight.decisions.no_pathway")
    try:
        return D.decide(session, ctx["org"]["org_id"], ctx["user"]["id"], entity_id=body.entity_id,
                        entity_name=body.entity_name, scenario=body.scenario, horizon=body.horizon,
                        action=body.action, rationale=body.rationale, value_eur=body.value_eur, signal=body.signal)
    except D.DecisionError as e:          # the only refusal here: an action no sector offers
        raise UserError("oversight.decisions.bad_action") from e


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
    except D.DecisionError as e:          # the only refusal here: an outcome other than included or dismissed
        raise UserError("oversight.decisions.bad_flag_outcome") from e
    return Response(status_code=204)


@router.get("/watchlist", summary="Exposures on the monitor watchlist")
def watchlist(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"watches": W.watchlist(session, ctx["org"]["org_id"])}


@router.post("/watchlist/recheck", summary="Re-check the watchlist now (escalates what worsened further)")
def recheck(session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    escalated = W.recheck_watchlist(session, ctx["org"]["org_id"], due_only=False)
    return {"escalated": escalated, "n": len(escalated)}


@router.post("/watchlist/{watch_id}/resolve", status_code=204, summary="Clear a watch (or mark it escalated)")
def resolve_watch(watch_id: str, session: DbSession, status: str = "cleared",
                  ctx: dict = Depends(require_permission("approvals.create"))):
    from fastapi import Response
    try:
        W.resolve_watch(session, ctx["org"]["org_id"], watch_id, ctx["user"]["id"], status)
    except W.WatchError as e:             # the only refusal here: an outcome other than cleared or escalated
        raise UserError("oversight.decisions.bad_watch_outcome") from e
    return Response(status_code=204)
