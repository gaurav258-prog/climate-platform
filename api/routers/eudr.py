"""EUDR records through the governed intake (Regulation (EU) 2023/1115; E92): the suppliers and customers, each
placing on the market / making available / export, and the plots each came from — template, dry run, upload — and the
movements on file. The due diligence statement is built on them (layers 3-5)."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, require_permission

router = APIRouter(prefix="/v1/eudr", tags=["EUDR"])
BOOKS = ("eudr_suppliers", "eudr_customers", "eudr_movements", "eudr_movement_plots")


def _book(book: str) -> str:
    if book not in BOOKS:
        raise HTTPException(404, {"error": "unknown_book", "message": f"the EUDR books are {', '.join(BOOKS)}"})
    return book


@router.get("/intake/{book}/template.xlsx", summary="The template of one EUDR book (Excel)")
def template(book: str):
    from services.intake.catalog import TEMPLATES
    from services.templates.workbook import build_template_workbook
    buf = build_template_workbook(TEMPLATES[_book(book)].specs(None))
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename={book}_template.xlsx"})


@router.post("/intake/{book}/validate", summary="Check an EUDR book before importing — nothing is saved")
async def validate(book: str, session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                   declared_row_count: Optional[str] = Form(None), mapping_profile_id: Optional[str] = Form(None)):
    from api.services.intake_http import declared_from_form, preview
    return preview(session, ctx["org"]["org_id"], _book(book), await file.read(), file.filename,
                   declared_from_form(declared_row_count, None), mapping_profile_id)


@router.post("/intake/{book}/upload", summary="Upload an EUDR book through the governed intake")
async def upload(book: str, session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                 declared_row_count: Optional[str] = Form(None), approval_reason: Optional[str] = Form(None),
                 mapping_profile_id: Optional[str] = Form(None)):
    from api.services.intake_http import declared_from_form, submit
    return submit(session, ctx["org"]["org_id"], _book(book), await file.read(), file.filename, user_id=ctx["user"]["id"],
                  declared=declared_from_form(declared_row_count, None), reason=approval_reason,
                  mapping_profile_id=mapping_profile_id)


@router.get("/movements", summary="Placings on the market, makings available and exports on file, with their plots")
def movements(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    rows = session.execute(text("""
        SELECT m.movement_id::text AS movement_id, m.external_ref, m.kind, m.actor_role, m.planned_on, m.hs_code,
               m.description, m.customs_flow, CAST(m.net_mass_kg AS FLOAT) AS net_mass_kg, s.name AS supplier, c.name AS customer,
               (SELECT count(*) FROM eudr_movement_plot l WHERE l.movement_id = m.movement_id) AS n_plots
        FROM eudr_movement m LEFT JOIN sc_suppliers s USING (supplier_id) LEFT JOIN sc_customers c USING (customer_id)
        WHERE m.org_id = CAST(:o AS uuid) ORDER BY m.planned_on DESC, m.seq DESC"""), {"o": ctx["org"]["org_id"]}).mappings().all()
    return {"movements": [{**dict(r), "planned_on": r["planned_on"].isoformat()} for r in rows]}


# ── the operator's records: status, legality evidence, plot readings, risk assessment; and the statement as it stands ──

class StatusBody(BaseModel):
    effective_from: date
    entity_id: Optional[str] = None
    size_class: str = Field(..., pattern="^(micro|small|medium|large)$")
    country: str = Field(..., min_length=2, max_length=2)
    address: str = Field(..., min_length=3, max_length=500)
    eori: Optional[str] = Field(None, max_length=17)
    established_on: Optional[date] = None
    basis: Optional[str] = Field(None, max_length=2000)


@router.post("/status", status_code=202, summary="State the undertaking's EUDR status (a second person approves)")
def state_status(body: StatusBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.eudr.records import RecordError, request_status
    try:
        out = request_status(session, ctx["org"]["org_id"], ctx["user"]["id"], **body.model_dump())
    except RecordError as e:
        raise HTTPException(422, {"error": "invalid_status", "message": str(e)}) from e
    session.commit()
    return out


class EvidenceBody(BaseModel):
    aspect: str
    document_kind: str = Field(..., min_length=2, max_length=200)
    plot_id: Optional[str] = None
    supplier_id: Optional[str] = None
    movement_id: Optional[str] = None
    document_ref: Optional[str] = Field(None, max_length=300)
    file_sha256: Optional[str] = Field(None, pattern="^[0-9a-f]{64}$")
    issued_by: Optional[str] = Field(None, max_length=300)
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    note: Optional[str] = Field(None, max_length=2000)
    withdraws: Optional[str] = None


@router.post("/evidence", status_code=201, summary="Record legality evidence (Art. 9(1)(h), 2(40)) — append-only")
def add_evidence(body: EvidenceBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.eudr.records import RecordError
    from services.eudr.records import add_evidence as add
    try:
        eid = add(session, ctx["org"]["org_id"], ctx["user"]["id"], **body.model_dump())
    except RecordError as e:
        raise HTTPException(422, {"error": "invalid_evidence", "message": str(e)}) from e
    session.commit()
    return {"evidence_id": eid}


class ReadBody(BaseModel):
    plot_ids: list[str] = Field(..., min_length=1, max_length=2000)
    treecover_min_pct: Optional[int] = Field(None, ge=1, le=100)
    point_radius_m: Optional[float] = Field(None, gt=0, le=5000)


@router.post("/plots/read", status_code=202, summary="Read plots against the satellite record (a job; each reading kept)")
def read_plots(body: ReadBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.tasks.jobs import submit
    org_id = ctx["org"]["org_id"]
    mine = {r[0] for r in session.execute(text("SELECT plot_id::text FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid) "
                                                "AND plot_id = ANY(CAST(:p AS uuid[]))"), {"o": org_id, "p": body.plot_ids}).all()}
    if mine != set(body.plot_ids):
        raise HTTPException(404, {"error": "unknown_plots", "message": "some plots are not in this organisation"})
    return submit("eudr.read_plots", org_id, body.plot_ids, ctx["user"]["id"], body.treecover_min_pct, body.point_radius_m)


class RiskBody(BaseModel):
    path: str = Field(..., pattern="^(full|simplified)$")
    conclusion: str = Field(..., pattern="^(negligible|not_negligible)$")
    criteria: dict[str, str] = Field(default_factory=dict)
    mitigation: dict[str, str] = Field(default_factory=dict)
    circumvention_mixing: Optional[str] = Field(None, max_length=5000)


@router.post("/movements/{movement_id}/risk-assessment", status_code=202,
             summary="State the risk assessment of a movement (Art. 10-11, or Art. 13) — a second person approves")
def assess(movement_id: str, body: RiskBody, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.eudr.records import RecordError, request_assessment
    try:
        out = request_assessment(session, ctx["org"]["org_id"], ctx["user"]["id"], movement_id=movement_id, **body.model_dump())
    except RecordError as e:
        raise HTTPException(422, {"error": "invalid_assessment", "message": str(e)}) from e
    session.commit()
    return out


@router.get("/movements/{movement_id}/statement", summary="The due diligence statement as it stands, with what it rests on")
def statement(movement_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.eudr.statement import StatementError, compute
    try:
        return compute(session, ctx["org"]["org_id"], movement_id)
    except StatementError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)}) from e
