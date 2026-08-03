"""Regulatory-change register API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
import services.governance.reg_changes as C

router = APIRouter(prefix="/v1/reg-changes", tags=["Regulatory changes"])


class ChangeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    framework: Optional[str] = None
    summary: Optional[str] = Field(None, max_length=4000)
    citation: Optional[str] = Field(None, max_length=400)
    owner: str = "platform"
    impact: Optional[str] = Field(None, max_length=2000)
    effective_date: Optional[str] = None
    org_scoped: bool = False


class Advance(BaseModel):
    stage: str


@router.get("/board", summary="Change register grouped by stage")
def board(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return C.board(session, ctx["org"]["org_id"])


@router.post("", status_code=201, summary="Register a regulatory change")
def create(body: ChangeCreate, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        return C.create_change(session, ctx["org"]["org_id"], ctx["user"]["id"], title=body.title,
                               framework=body.framework, summary=body.summary, citation=body.citation,
                               owner=body.owner, impact=body.impact, effective_date=body.effective_date,
                               org_scoped=body.org_scoped)
    except C.ChangeError as e:
        raise HTTPException(409, {"error": "change_error", "message": str(e)})


@router.post("/{change_id}/advance", summary="Move a change to another stage")
def advance(change_id: str, body: Advance, session: DbSession,
            ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        return C.advance(session, change_id, body.stage)
    except C.ChangeError as e:
        raise HTTPException(409, {"error": "change_error", "message": str(e)})
