"""An undertaking's ESRS statement (E1, E3, E4), live: every item of the version governing the financial year with its
figures (computed, stated, derived), the undertaking's answers and omissions, its CSRD role and whether Art. 5(2)
requires the statement — and the checks the filing will run. Filed versions go through the ordinary filing lifecycle
(report type esrs_pack), frozen by services.governance.esrs_document.freeze."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import DbSession, own_or_404, require_permission
from services.governance import esrs_document as D

router = APIRouter(prefix="/v1/esrs", tags=["ESRS statement"])


def _period_end(session, org_id: str):
    from services.governance.filings import reporting_period_end
    return reporting_period_end(session, org_id)


@router.get("/statement", summary="The statement as it stands now for an undertaking (or the organisation), with its checks")
def statement(session: DbSession, entity_id: Optional[str] = Query(None),
              ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.esrs_checks import checks, phase_ins
    org_id = ctx["org"]["org_id"]
    if entity_id:
        own_or_404(session, "reporting_entities", "entity_id", entity_id, org_id, "Reporting entity")
    pe = _period_end(session, org_id)
    try:
        spec = D.governing(session, org_id, pe)
        out = D.freeze(session, org_id, entity_ids=[entity_id] if entity_id else None, period_end=pe)
    except D.DocumentError as e:
        raise HTTPException(status_code=422, detail={"error": "not_applicable", "message": str(e)}) from e
    rec = {"version": spec["version"], "act": spec["act"]["short"]}
    return {**out, "spec": rec, "checks": checks({**out, "_specs": {"esrs": rec}}),
            "phase_ins": [{"id": r["id"], "ref": r["ref"], "quote": r["quote"]} for r in phase_ins(spec["version"])]}


class Answers(BaseModel):
    standard: str = Field(..., pattern="^(E1|E3|E4|materiality|comparatives)$")
    answers: dict[str, Any]
    entity_id: Optional[str] = None


@router.put("/answers", summary="Answer items of one standard, or the topic materiality (keyed by item id; null clears one)")
def put_answers(body: Answers, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    org_id = ctx["org"]["org_id"]
    if body.entity_id:
        own_or_404(session, "reporting_entities", "entity_id", body.entity_id, org_id, "Reporting entity")
    try:
        out = D.save(session, org_id, ctx["user"]["id"], entity_id=body.entity_id, period_end=_period_end(session, org_id),
                     standard=body.standard, answers=body.answers)
    except (D.DocumentError, D.TA.AnswerError) as e:
        raise HTTPException(status_code=422, detail={"error": "not_applicable", "message": str(e)}) from e
    session.commit()
    if out["refused"] and not out["saved"]:
        raise HTTPException(status_code=422, detail={"error": "refused", "message": out["refused"][0]["reason"],
                                                     "refused": out["refused"]})
    return out
