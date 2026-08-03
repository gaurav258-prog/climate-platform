"""RConnect — submission case & regulator-communication API."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
import services.governance.rconnect as R

router = APIRouter(prefix="/v1/rconnect", tags=["RConnect"])


class CaseOpen(BaseModel):
    regulator: str = Field(..., min_length=1, max_length=200)
    filing_id: Optional[str] = None
    reference: Optional[str] = Field(None, max_length=200)


class StageBody(BaseModel):
    stage: str


class MessageBody(BaseModel):
    direction: str
    author: str = Field(..., max_length=120)
    body: str = Field(..., min_length=1, max_length=4000)
    attachment_ref: Optional[str] = Field(None, max_length=200)


@router.get("/cases", summary="Submission cases")
def cases(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"cases": R.list_cases(session, ctx["org"]["org_id"])}


@router.get("/cases/{case_id}", summary="One case with its communication thread")
def case(case_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    c = R.get_case(session, ctx["org"]["org_id"], case_id)
    if not c:
        raise HTTPException(404, {"error": "not_found", "message": "Case not found."})
    return c


@router.post("/cases", status_code=201, summary="Open a submission case")
def open_case(body: CaseOpen, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        return R.open_case(session, ctx["org"]["org_id"], ctx["user"]["id"],
                           regulator=body.regulator, filing_id=body.filing_id, reference=body.reference)
    except R.CaseError as e:
        raise HTTPException(409, {"error": "case_error", "message": str(e)})


@router.post("/cases/{case_id}/stage", summary="Advance the case stage")
def stage(case_id: str, body: StageBody, session: DbSession,
          ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        return R.advance_stage(session, ctx["org"]["org_id"], case_id, ctx["user"]["id"], body.stage)
    except R.CaseError as e:
        raise HTTPException(409, {"error": "case_error", "message": str(e)})


@router.post("/cases/{case_id}/message", status_code=201, summary="Log a message on the case")
def message(case_id: str, body: MessageBody, session: DbSession,
            ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        return R.post_message(session, ctx["org"]["org_id"], case_id, ctx["user"]["id"],
                              direction=body.direction, author=body.author, body=body.body,
                              attachment_ref=body.attachment_ref)
    except R.CaseError as e:
        raise HTTPException(409, {"error": "case_error", "message": str(e)})
