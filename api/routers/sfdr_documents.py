"""A fund's SFDR pre-contractual and periodic documents (RTS 2022/1288 Annexes II–V), live: every item of the governing
template with its value, the manager's answers to the items the platform cannot know, and the annex as a document.
Filed versions go through the ordinary filing lifecycle (report types sfdr_precontractual / sfdr_periodic)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.deps import DbSession, own_or_404, require_permission
from api.routers.funds import OrgId
from services.governance import sfdr_answers as A

router = APIRouter(prefix="/v1", tags=["Asset Management — Funds"])


def _doc(session, org_id: str, fund_id: str, document: str) -> dict:
    try:
        return A.live(session, org_id, fund_id, document)
    except A.AnswerError as e:
        raise HTTPException(status_code=422, detail={"error": "not_applicable", "message": str(e)}) from e


@router.get("/funds/{fund_id}/sfdr-documents/{document}",
            summary="The fund's SFDR pre-contractual or periodic template, item by item, as it stands now")
def get_document(fund_id: str, document: str, session: DbSession, org_id: OrgId):
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    return _doc(session, org_id, fund_id, document)


@router.get("/funds/{fund_id}/sfdr-documents/{document}/annex.html", response_class=HTMLResponse,
            summary="The template as the document annexed to the prospectus / annual report (draft, not filed)")
def get_document_html(fund_id: str, document: str, session: DbSession, org_id: OrgId):
    from services.governance.sfdr_product_html import render
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    d = _doc(session, org_id, fund_id, document)
    return HTMLResponse(render(d["title"], d["citation"], d["fund"], d["items"], d["period_end"]))


class Answers(BaseModel):
    answers: dict[str, Any]


@router.put("/funds/{fund_id}/sfdr-documents/{document}/answers",
            summary="Answer template items (keyed by the item's id; null clears one) — refused answers are reported")
def put_answers(fund_id: str, document: str, body: Answers, session: DbSession,
                ctx: dict = Depends(require_permission("approvals.create"))):
    org_id = ctx["org"]["org_id"]                      # a signed-in preparer's own organisation (never the demo)
    own_or_404(session, "funds", "fund_id", fund_id, org_id, "Fund")
    try:
        out = A.save(session, org_id, fund_id, document, body.answers, ctx["user"]["id"])
    except A.AnswerError as e:
        raise HTTPException(status_code=422, detail={"error": "not_applicable", "message": str(e)}) from e
    session.commit()
    if out["refused"] and not out["saved"]:
        raise HTTPException(status_code=422, detail={"error": "refused", "message": "no answer could be saved",
                                                     "refused": out["refused"]})
    return {**out, "document": A.live(session, org_id, fund_id, document)}
