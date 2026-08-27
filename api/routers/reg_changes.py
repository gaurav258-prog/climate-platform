"""Regulatory-change register API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import services.governance.reg_changes as C
from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/reg-changes", tags=["Regulatory changes"])


class ChangeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    framework: Optional[str] = None
    summary: Optional[str] = Field(None, max_length=4000)
    citation: Optional[str] = Field(None, max_length=400)
    owner: str = "tenant"
    impact: Optional[str] = Field(None, max_length=2000)
    effective_date: Optional[str] = None
    # a tenant endpoint never creates a platform-wide (NULL) change — those are platform-seeded


class Advance(BaseModel):
    stage: str


@router.get("/board", summary="Change register grouped by stage")
def board(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return C.board(session, ctx["org"]["org_id"])


@router.get("/outlook", summary="Regulatory outlook (customer view) — what's in force today, and what's changing when + any data you'll need")
def outlook(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.reg_outlook import outlook as _outlook
    return _outlook(ctx["org"].get("type"), session, ctx["org"]["org_id"])


@router.get("/versions", summary="CRCS version register — each regulation's version lineage (base + amendments), what's in force now and what's coming")
def versions(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.reg_versions import versions as _versions
    return _versions(session, ctx["org"].get("type"))


@router.get("/alerts", summary="Proactive regulatory alerts raised for this org (detected changes / approaching deadlines)")
def alerts(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.reg_alerts import list_alerts
    return {"alerts": list_alerts(session, ctx["org"]["org_id"])}


@router.post("/alerts/sweep", summary="Run the alert sweep now — raise any new alerts (task + email + webhook)")
def sweep_alerts(session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    from services.governance.reg_alerts import sweep
    return sweep(session, ctx["org"]["org_id"], ctx["org"].get("type"))


@router.post("", status_code=201, summary="Register a regulatory change")
def create(body: ChangeCreate, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        return C.create_change(session, ctx["org"]["org_id"], ctx["user"]["id"], title=body.title,
                               framework=body.framework, summary=body.summary, citation=body.citation,
                               owner=body.owner, impact=body.impact, effective_date=body.effective_date,
                               org_scoped=True)
    except C.ChangeError as e:
        raise HTTPException(409, {"error": "change_error", "message": str(e)})


@router.post("/{change_id}/advance", summary="Move a change to another stage")
def advance(change_id: str, body: Advance, session: DbSession,
            ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        return C.advance(session, ctx["org"]["org_id"], change_id, body.stage)
    except C.ChangeError as e:
        raise HTTPException(409, {"error": "change_error", "message": str(e)})
