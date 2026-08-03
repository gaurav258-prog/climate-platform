"""Reporting cockpit — the regulatory filing register, lifecycle and obligations calendar.

The lifecycle maps onto existing permissions and machinery:
  - prepare / submit-for-review   → approvals.create (the maker)
  - approve                       → done through /v1/approvals/{id}/decide (approvals.decide, checker ≠ maker)
  - attest / submit / accept      → reports.publish (the accountable person)
  - view                         → reports.view

Nothing here re-freezes a report: generate wraps report_snapshots.create_snapshot, so the frozen bytes are
the same immutable, hashed, versioned record the assurance pack already verifies.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.governance import filings as F

router = APIRouter(prefix="/v1", tags=["Reporting cockpit"])


class GenerateBody(BaseModel):
    framework: str = Field(..., min_length=1, max_length=60)
    note: Optional[str] = Field(None, max_length=500)


class AttestBody(BaseModel):
    attestor_name: str = Field(..., min_length=1, max_length=200)
    statement: str = Field(..., min_length=1, max_length=2000)


class SubmitBody(BaseModel):
    submission_ref: Optional[str] = Field(None, max_length=200)


class AcceptBody(BaseModel):
    ack_ref: Optional[str] = Field(None, max_length=200)


def _audit(session, ctx, action, filing_id, detail=None):
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action=action, target_type="filing", target_id=str(filing_id), detail=detail or {})


# ── read surfaces ───────────────────────────────────────────────────────

@router.get("/obligations", summary="Regulatory filing calendar — what's due, by when")
def obligations(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"obligations": F.list_obligations(session, ctx["org"]["org_id"], ctx["org"]["type"])}


@router.get("/filings/frameworks", summary="Frameworks this organisation can file")
def frameworks(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"frameworks": F.available_frameworks(ctx["org"]["type"])}


@router.get("/filings", summary="The filing register — every filing, newest first")
def list_filings(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return {"filings": F.list_filings(session, ctx["org"]["org_id"])}


@router.get("/filings/{filing_id}", summary="One filing — status, full history, and the frozen report")
def get_filing(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    f = F.get_filing(session, ctx["org"]["org_id"], filing_id)
    if not f:
        raise HTTPException(404, {"error": "not_found", "message": "Filing not found."})
    return f


@router.get("/filings/{filing_id}/validation", summary="Run the pre-submission validation checklist")
def validation(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_validation import validate_filing
    try:
        return validate_filing(session, ctx["org"]["org_id"], filing_id)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/filings/{filing_id}/lineage/hazards", summary="The hazard cells a filing reports (trace entry points)")
def lineage_hazards(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_lineage import reported_hazards
    try:
        return {"hazards": reported_hazards(session, ctx["org"]["org_id"], filing_id)}
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/filings/{filing_id}/lineage", summary="Forward trace: a reported cell → assets → golden source → feeds")
def lineage(filing_id: str, hazard: str, session: DbSession,
            ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_lineage import cell_lineage
    try:
        return cell_lineage(session, ctx["org"]["org_id"], filing_id, hazard)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/lineage/cell/{h3_cell}", summary="Reverse trace: a granular cell → every holding & filing that reuses it")
def lineage_cell(h3_cell: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.governance.filing_lineage import cell_upstream
    return cell_upstream(session, ctx["org"]["org_id"], h3_cell)


# ── lifecycle ───────────────────────────────────────────────────────────

@router.post("/filings", status_code=201, summary="Generate a draft filing (freezes the report)")
def generate(body: GenerateBody, session: DbSession,
             ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        f = F.generate_filing(session, ctx["org"]["org_id"], ctx["org"]["type"],
                              body.framework, ctx["user"]["id"], note=body.note)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.generate", f["filing_id"], {"framework": body.framework})
    return f


@router.post("/filings/{filing_id}/submit-for-review", summary="Submit a draft for 4-eyes approval (maker)")
def submit_for_review(filing_id: str, session: DbSession,
                      ctx: dict = Depends(require_permission("approvals.create"))):
    try:
        f = F.submit_for_review(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"])
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.submit_for_review", filing_id)
    return f


@router.post("/filings/{filing_id}/attest", summary="Attest the filing — named accountable sign-off")
def attest(filing_id: str, body: AttestBody, session: DbSession,
           ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        f = F.attest(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"],
                     body.attestor_name, body.statement)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.attest", filing_id, {"attestor_name": body.attestor_name})
    return f


@router.post("/filings/{filing_id}/submit", summary="Transmit the filing to the regulator")
def submit(filing_id: str, body: SubmitBody, session: DbSession,
           ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        f = F.submit(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.submission_ref)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.submit", filing_id, {"submission_ref": body.submission_ref})
    return f


@router.post("/filings/{filing_id}/accept", summary="Record the regulator's acknowledgement")
def accept(filing_id: str, body: AcceptBody, session: DbSession,
           ctx: dict = Depends(require_permission("reports.publish"))):
    try:
        f = F.accept(session, ctx["org"]["org_id"], filing_id, ctx["user"]["id"], body.ack_ref)
    except F.FilingError as e:
        raise HTTPException(409, {"error": "filing_error", "message": str(e)})
    _audit(session, ctx, "filing.accept", filing_id, {"ack_ref": body.ack_ref})
    return f
