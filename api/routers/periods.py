"""Reporting periods: the year-end close of an undertaking and the restatement of a closed period's values
(services.governance.period_close). Both are requested by one person and take effect when a second approves."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.governance import period_close as PC

router = APIRouter(prefix="/v1/periods", tags=["periods"])


class CloseBody(BaseModel):
    period_end: date
    entity_id: Optional[str] = Field(None, description="The undertaking (Admin → Entities); none = the organisation itself.")
    note: Optional[str] = Field(None, max_length=2000)


class RestateSiteValue(BaseModel):
    site_id: str
    period_end: date
    measure: str = Field(..., pattern="^(carrying_amount|net_revenue)$")
    amount: float = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3)
    reason: str = Field(..., min_length=10, max_length=2000)


@router.get("", summary="The organisation's closed reporting periods")
def list_closes(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"closes": PC.closes(session, ctx["org"]["org_id"])}


@router.get("/close/blockers", summary="What stops a period from closing now")
def blockers(period_end: date, session: DbSession, entity_id: Optional[str] = None,
             ctx: dict = Depends(require_permission("reports.view"))):
    return {"blockers": PC.close_blockers(session, ctx["org"]["org_id"], entity_id, period_end)}


@router.post("/close", status_code=202, summary="Ask to close a reporting period (a second person approves)")
def request_close(body: CloseBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        out = PC.request_close(session, ctx["org"]["org_id"], ctx["user"]["id"], entity_id=body.entity_id,
                               period_end=body.period_end, note=body.note)
    except PC.PeriodError as e:
        raise HTTPException(409, {"error": "cannot_close", "message": str(e)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="period.close.request",
                target_type="period", target_id=None, detail={"period_end": body.period_end.isoformat(), "entity_id": body.entity_id})
    return out


@router.post("/restatements/site-value", status_code=202,
             summary="Restate a closed period's site carrying amount or net revenue (a second person approves)")
def restate_site_value(body: RestateSiteValue, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        out = PC.request_site_value_restatement(session, ctx["org"]["org_id"], ctx["user"]["id"], site_id=body.site_id,
                                                period_end=body.period_end, measure=body.measure, amount=body.amount,
                                                currency=body.currency, reason=body.reason)
    except PC.PeriodError as e:
        raise HTTPException(409, {"error": "cannot_restate", "message": str(e)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="period.restate.request",
                target_type="company_site", target_id=body.site_id,
                detail={"period_end": body.period_end.isoformat(), "measure": body.measure})
    return out
