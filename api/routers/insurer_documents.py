"""An insurer's document reports, live — the ORSA climate change scenario analysis (Art. 45a) and the pre-emptive
recovery plan's nat-cat stress and capital indicators (IRRD Art. 5(7)-(8)): every item of the governing template with
its value, and the undertaking's answers to the items only it can give. Filed versions go through the ordinary filing
lifecycle (report types insurer_orsa_climate / insurer_recovery_stress)."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.deps import DbSession, own_or_404, require_permission
from core.errors import UserError
from services.governance import insurer_documents as D

router = APIRouter(prefix="/v1/insurance/documents", tags=["Insurance — Solvency II documents"])


def _period_end(session, org_id: str) -> date:
    from services.governance.filings import reporting_period_end
    return reporting_period_end(session, org_id)


def _filer_or_refuse(session, org_id: str, report_type: str, entity_id: Optional[str]) -> None:
    """A document is one filer's: the whole organisation of two or more entities is refused with its filers
    (services.governance.report_filers), as the filing is."""
    from services.governance.report_filers import whole_org_refusal
    why = whole_org_refusal(session, org_id, report_type, entity_id, _period_end(session, org_id))
    if why is not None:
        raise UserError(why[0], 409, **why[1])


@router.get("/{report_type}", summary="The document as it stands now, item by item, for an undertaking or the group")
def get_document(report_type: str, session: DbSession, entity_id: Optional[str] = Query(None),
                 disclosure_date: Optional[date] = Query(None, description="the date the report will be made (it chooses the rules)"),
                 ctx: dict = Depends(require_permission("reports.view"))):
    org_id = ctx["org"]["org_id"]
    if entity_id:
        own_or_404(session, "reporting_entities", "entity_id", entity_id, org_id, "Reporting entity")
    _filer_or_refuse(session, org_id, report_type, entity_id)
    try:
        return D.live(session, org_id, report_type, entity_id=entity_id, period_end=_period_end(session, org_id),
                      disclosure_date=disclosure_date)
    except D.DocumentError as e:
        raise UserError(e.code, e.status, **e.params) from e


class Answers(BaseModel):
    answers: dict[str, Any]
    entity_id: Optional[str] = None
    disclosure_date: Optional[date] = None


@router.put("/{report_type}/answers", summary="Answer the undertaking's items (keyed by item id; null clears one)")
def put_answers(report_type: str, body: Answers, session: DbSession,
                ctx: dict = Depends(require_permission("approvals.create"))):
    org_id = ctx["org"]["org_id"]
    if body.entity_id:
        own_or_404(session, "reporting_entities", "entity_id", body.entity_id, org_id, "Reporting entity")
    _filer_or_refuse(session, org_id, report_type, body.entity_id)
    try:
        out = D.save(session, org_id, report_type, body.answers, ctx["user"]["id"], entity_id=body.entity_id,
                     period_end=_period_end(session, org_id), disclosure_date=body.disclosure_date)
    except D.DocumentError as e:
        raise UserError(e.code, e.status, **e.params) from e
    session.commit()
    if out["refused"] and not out["saved"]:
        raise UserError("disclose.answers.refused_all", n=len(out["refused"]), first=out["refused"][0]["msg"]["label"])
    return out
