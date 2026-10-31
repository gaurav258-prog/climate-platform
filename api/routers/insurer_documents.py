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


def _filer_or_refuse(session, org_id: str, report_type: str, entity_id: Optional[str], filing_role: Optional[str]) -> str:
    """A document is one filer's report, as the filing is: the whole organisation that records its undertakings is
    refused with its filers (services.governance.report_filers), and a role the scope cannot take (filings._scope_role —
    a parent's own report only where the report offers one, a group's only for an entity with entities below it).
    → the scope's role (a parent's own 'solo', or its group's)."""
    from services.governance.filings import _scope_role
    from services.governance.report_filers import whole_org_refusal
    why = whole_org_refusal(session, org_id, report_type, entity_id, _period_end(session, org_id))
    if why is not None:
        raise UserError(why[0], 409, **why[1])
    return _scope_role(session, org_id, report_type, entity_id, filing_role)


@router.get("/{report_type}", summary="The document as it stands now, item by item, for an undertaking or the group")
def get_document(report_type: str, session: DbSession, entity_id: Optional[str] = Query(None),
                 filing_role: Optional[str] = Query(None, description="which of the entity's reports, where it holds two: "
                                                                      "'solo' (its own) or 'consolidated' (its group's)"),
                 disclosure_date: Optional[date] = Query(None, description="the date the report will be made (it chooses the rules)"),
                 ctx: dict = Depends(require_permission("reports.view"))):
    org_id = ctx["org"]["org_id"]
    if entity_id:
        own_or_404(session, "reporting_entities", "entity_id", entity_id, org_id, "Reporting entity")
    role = _filer_or_refuse(session, org_id, report_type, entity_id, filing_role)
    try:
        return D.live(session, org_id, report_type, entity_id=entity_id, period_end=_period_end(session, org_id),
                      disclosure_date=disclosure_date, role=role)
    except D.DocumentError as e:
        raise UserError(e.code, e.status, **e.params) from e


class Answers(BaseModel):
    answers: dict[str, Any]
    entity_id: Optional[str] = None
    filing_role: Optional[str] = None          # which of the entity's reports, where it holds two (an ORSA's own or group's)
    disclosure_date: Optional[date] = None


@router.put("/{report_type}/answers", summary="Answer the undertaking's items (keyed by item id; null clears one)")
def put_answers(report_type: str, body: Answers, session: DbSession,
                ctx: dict = Depends(require_permission("approvals.create"))):
    org_id = ctx["org"]["org_id"]
    if body.entity_id:
        own_or_404(session, "reporting_entities", "entity_id", body.entity_id, org_id, "Reporting entity")
    role = _filer_or_refuse(session, org_id, report_type, body.entity_id, body.filing_role)
    try:
        out = D.save(session, org_id, report_type, body.answers, ctx["user"]["id"], entity_id=body.entity_id,
                     period_end=_period_end(session, org_id), disclosure_date=body.disclosure_date, role=role)
    except D.DocumentError as e:
        raise UserError(e.code, e.status, **e.params) from e
    session.commit()
    if out["refused"] and not out["saved"]:
        raise UserError("disclose.answers.refused_all", n=len(out["refused"]), first=out["refused"][0]["msg"]["label"])
    return out
