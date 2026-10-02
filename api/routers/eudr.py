"""EUDR records through the governed intake (Regulation (EU) 2023/1115; E92): the suppliers and customers, each
placing on the market / making available / export, and the plots each came from — template, dry run, upload — and the
movements on file. The due diligence statement is built on them (layers 3-5)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, attachment, require_permission

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
                             headers={"Content-Disposition": attachment(f"{book}_template.xlsx")})


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
    # each shipment's statements, newest first (regulatory_filing has no sequence; each statement of a shipment is
    # prepared in its own request, so created_at never ties within one shipment)
    filings: dict[str, list[dict]] = {}
    for f in session.execute(text("""
        SELECT f.eudr_movement_id::text AS movement_id, f.filing_id::text AS filing_id, f.status,
               r.reference_number, r.verification_number
        FROM regulatory_filing f
        LEFT JOIN LATERAL (SELECT reference_number, verification_number FROM eudr_dds_reference x
                           WHERE x.filing_id = f.filing_id ORDER BY x.seq DESC LIMIT 1) r ON true
        WHERE f.org_id = CAST(:o AS uuid) AND f.framework = 'eudr_dds'
        ORDER BY f.created_at DESC, f.filing_id"""), {"o": ctx["org"]["org_id"]}).mappings().all():
        filings.setdefault(f["movement_id"], []).append({k: f[k] for k in ("filing_id", "status", "reference_number",
                                                                          "verification_number")})
    return {"movements": [{**dict(r), "planned_on": r["planned_on"].isoformat(), "filings": filings.get(r["movement_id"], [])}
                          for r in rows]}


# ── the operator's records: status, legality evidence, plot readings, risk assessment; and the statement as it stands ──

@router.get("/records", summary="The undertaking's EUDR status on a date, and the lists its records are stated against")
def records(session: DbSession, on: Optional[date] = None, entity_id: Optional[str] = None,
            ctx: dict = Depends(require_permission("reports.view"))):
    from services.eudr import records as REC
    from services.eudr.reading import current, tally
    org = ctx["org"]["org_id"]
    st = REC.live_status(session, org, entity_id, on or date.today())
    plots = [dict(r) for r in session.execute(text("""
        SELECT p.plot_id::text AS plot_id, p.plot_name, p.external_ref, co.name AS commodity, p.country,
               CAST(p.plot_area_ha AS FLOAT) AS area_ha, p.plot_geometry IS NOT NULL AS has_polygon
        FROM sc_sourcing_plots p JOIN sc_commodities co USING (commodity_id)
        WHERE p.org_id = CAST(:o AS uuid) AND co.eudr_covered ORDER BY p.plot_name"""), {"o": org}).mappings().all()]
    readings = current(session, [p["plot_id"] for p in plots]) if plots else {}
    # requests a second person has not decided yet (status; risk assessments by shipment)
    pending = [dict(x) for x in session.execute(text("""
        SELECT request_id::text AS request_id, request_type, title, payload->>'movement_id' AS movement_id
        FROM approval_requests WHERE org_id = CAST(:o AS uuid) AND status = 'pending' AND request_type IN ('eudr.status', 'eudr.risk')
        ORDER BY created_at"""), {"o": org}).mappings().all()]
    return {"status": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in st.items()} if st else None,
            "on": (on or date.today()).isoformat(),
            "criteria": REC.CRITERIA, "mitigation": REC.MITIGATION, "aspects": list(REC.ASPECTS),
            "size_classes": list(REC.SIZE_CLASSES),
            "plots": [{**p, "reading": readings.get(p["plot_id"])} for p in plots], "readings_tally": tally(readings),
            "pending": pending}


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


@router.get("/movements/{movement_id}/statement",
            summary="The due diligence statement as it stands, what it rests on, and the checks the filing will run")
def statement(movement_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.eudr.checks import checks
    from services.eudr.statement import StatementError, compute
    try:
        st = compute(session, ctx["org"]["org_id"], movement_id)
    except StatementError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)}) from e
    return {**st, "checks": checks(st)}


class ScopeBody(BaseModel):
    in_scope: bool
    basis: str = Field(..., min_length=10, max_length=2000)


@router.put("/movements/{movement_id}/scope", summary="State whether the product is in Annex I where the annex leaves it open")
def state_scope(movement_id: str, body: ScopeBody, session: DbSession,
                ctx: dict = Depends(require_permission("approvals.create"))):
    """Only where Annex I leaves it open (an 'ex' heading, or a row that excepts part of what it names): the operator's
    own statement about its product, with why. Refused once the movement's statement is under review (database)."""
    from services.eudr.statement import compute
    org_id = ctx["org"]["org_id"]
    st = compute(session, org_id, movement_id)
    if st["scope"].get("in_scope") is not None:
        raise HTTPException(409, {"error": "not_open", "message": f"Annex I decides this product: {st['scope'].get('why')}"})
    session.execute(text("UPDATE eudr_movement SET scope_in = :i, scope_basis = :b WHERE movement_id = CAST(:m AS uuid) "
                         "AND org_id = CAST(:o AS uuid)"), {"i": body.in_scope, "b": body.basis, "m": movement_id, "o": org_id})
    session.commit()
    return {"in_scope": body.in_scope}


# ── the statement as a filing (services/eudr/filing.py); review, approval, attestation, submission: /v1/filings/{id}/… ──

def _fail(e: Exception, code: int = 409):
    raise HTTPException(code, {"error": "eudr_filing", "message": str(e)}) from e


class PrepareBody(BaseModel):
    note: Optional[str] = Field(None, max_length=500)


@router.post("/movements/{movement_id}/filing", status_code=201, summary="Prepare the shipment's due diligence statement")
def prepare_filing(movement_id: str, body: PrepareBody, session: DbSession,
                   ctx: dict = Depends(require_permission("reports.publish"))):
    from services.eudr.filing import EudrFilingError, prepare
    try:
        out = prepare(session, ctx["org"]["org_id"], ctx["user"]["id"], movement_id, note=body.note)
    except EudrFilingError as e:
        _fail(e)
    session.commit()
    return out


@router.post("/filings/{filing_id}/refresh", summary="Replace a draft statement after its shipment was corrected")
def refresh_filing(filing_id: str, body: PrepareBody, session: DbSession,
                   ctx: dict = Depends(require_permission("reports.publish"))):
    from services.eudr.filing import EudrFilingError, refresh
    try:
        out = refresh(session, ctx["org"]["org_id"], ctx["user"]["id"], filing_id, note=body.note)
    except EudrFilingError as e:
        _fail(e)
    session.commit()
    return out


class ReferenceBody(BaseModel):
    reference_number: str = Field(..., min_length=4, max_length=64)
    verification_number: Optional[str] = Field(None, max_length=64)
    source: str = Field("manual_entry", pattern="^(information_system|manual_entry|contingency)$")


@router.post("/filings/{filing_id}/reference", summary="Record the reference and verification numbers made available")
def record_reference(filing_id: str, body: ReferenceBody, session: DbSession,
                     ctx: dict = Depends(require_permission("reports.publish"))):
    from services.eudr.filing import EudrFilingError
    from services.eudr.filing import record_reference as rec
    try:
        out = rec(session, ctx["org"]["org_id"], ctx["user"]["id"], filing_id, **body.model_dump())
    except EudrFilingError as e:
        _fail(e)
    session.commit()
    return out


class EventBody(BaseModel):
    kind: str
    detail: Optional[str] = Field(None, max_length=1000)
    until: Optional[datetime] = None


@router.post("/filings/{filing_id}/events", status_code=201, summary="Record what happened to a filed statement")
def record_event(filing_id: str, body: EventBody, session: DbSession,
                 ctx: dict = Depends(require_permission("reports.publish"))):
    from services.eudr.filing import EudrFilingError
    from services.eudr.filing import record_event as rec
    try:
        out = rec(session, ctx["org"]["org_id"], ctx["user"]["id"], filing_id, body.kind, detail=body.detail, until=body.until)
    except EudrFilingError as e:
        _fail(e)
    session.commit()
    return out


@router.get("/filings/{filing_id}/window", summary="Whether the statement may still be amended or withdrawn, and its events")
def filing_window(filing_id: str, session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    from services.eudr.filing import EudrFilingError, _filing, events, window
    try:
        _filing(session, ctx["org"]["org_id"], filing_id)
    except EudrFilingError as e:
        _fail(e, 404)
    return {"window": window(session, filing_id), "events": events(session, filing_id)}


class WithdrawBody(BaseModel):
    reason: str = Field(..., min_length=10, max_length=2000)


@router.post("/filings/{filing_id}/withdraw", summary="Withdraw a statement within the information system's window")
def withdraw_filing(filing_id: str, body: WithdrawBody, session: DbSession,
                    ctx: dict = Depends(require_permission("reports.publish"))):
    from services.eudr.filing import EudrFilingError, withdraw
    try:
        out = withdraw(session, ctx["org"]["org_id"], ctx["user"]["id"], filing_id, body.reason)
    except EudrFilingError as e:
        _fail(e)
    session.commit()
    return out


@router.post("/filings/{filing_id}/amend", status_code=201, summary="Amend a statement within the window (a new draft)")
def amend_filing(filing_id: str, body: PrepareBody, session: DbSession,
                 ctx: dict = Depends(require_permission("reports.publish"))):
    from services.eudr.filing import EudrFilingError, amend
    try:
        out = amend(session, ctx["org"]["org_id"], ctx["user"]["id"], filing_id, note=body.note)
    except EudrFilingError as e:
        _fail(e)
    session.commit()
    return out
