"""EUDR records through the governed intake (Regulation (EU) 2023/1115; E92): the suppliers and customers, each
placing on the market / making available / export, and the plots each came from — template, dry run, upload — and the
movements on file. The due diligence statement is built on them (layers 3-5)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
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
