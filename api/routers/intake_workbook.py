"""The standard workbook per sector (the product owner's decision of 2026-10-23): the blank file, its check, and its
upload — every sheet through the same intake pipeline as a single book (services/intake/workbooks.py). Systems send the
same books by the API (POST /v1/ingest/books/{template}), from the same field definitions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from api.deps import CurrentUser, DbSession, attachment
from core.errors import UserError

router = APIRouter(prefix="/v1/intake", tags=["Integration"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _sector(org_type: Optional[str]) -> str:
    from services.intake.workbooks import books
    try:
        books(org_type or "")
    except ValueError as e:
        raise UserError("intake.workbook.no_sector") from e
    return org_type


@router.get("/workbooks/{sector}.xlsx", summary="The standard data file of a sector (blank)")
def workbook(sector: str):
    from services.intake.workbooks import build
    return StreamingResponse(build(_sector(sector)), media_type=XLSX,
                             headers={"Content-Disposition": attachment(f"tellumen_{sector}_standard_file.xlsx")})


@router.get("/workbook/sheets", summary="The books of your sector's standard file and their fields")
def workbook_sheets(ctx: CurrentUser):
    from core import messages
    from services.intake.catalog import template_fields
    from services.intake.workbooks import books
    sector = _sector(ctx["org"].get("type"))
    return {"sector": sector, "about": messages.render("intake.workbook.start", sector=messages.name("admin.sector", sector)),
            "sheets": [{"sheet": t.sheet_name, "book": t.key, "about": messages.render(f"intake.book.{t.key}"),
                        "fields": template_fields(t.key)} for t in books(ctx["org"]["type"])]}


async def _read(file: UploadFile) -> bytes:
    raw = await file.read()
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise UserError("intake.workbook.not_xlsx")
    return raw


@router.post("/workbook/check", summary="Check your standard file, sheet by sheet — nothing is saved")
async def workbook_check(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                         currency: Optional[str] = Form(None), book_date: Optional[str] = Form(None)):
    from services.intake import workbooks
    raw = await _read(file)
    try:
        return workbooks.check(session, ctx["org"]["org_id"], _sector(ctx["org"].get("type")), raw, file.filename,
                               currency=currency or None, book_date=book_date or None)
    except workbooks.WorkbookError as e:
        raise UserError("intake.workbook.unreadable") from e


@router.post("/workbook", summary="Send your standard file: each sheet becomes a batch, checked and imported")
async def workbook_submit(session: DbSession, ctx: CurrentUser, file: UploadFile = File(...),
                          approval_reason: Optional[str] = Form(None), currency: Optional[str] = Form(None),
                          book_date: Optional[str] = Form(None)):
    """Every sheet with rows is received as its own batch: stored, security-inspected, malware-scanned and checked like a
    single book. A sheet that passes is imported and its scores and losses start by themselves; one whose check fails
    goes to a second person with your reason; one refused says why. One sheet never stops the next."""
    from services.intake import workbooks
    raw = await _read(file)
    try:
        return workbooks.submit(session, ctx["org"]["org_id"], _sector(ctx["org"].get("type")), raw, file.filename,
                                user_id=ctx["user"]["id"], reason=approval_reason, currency=currency or None,
                                book_date=book_date or None)
    except workbooks.WorkbookError as e:
        raise UserError("intake.workbook.unreadable") from e
