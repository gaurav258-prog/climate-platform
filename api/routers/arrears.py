"""Seasonal-arrears overlay — upload the agri book's days-past-due and see which past-dues are normal
harvest-cycle carry-over vs genuine deterioration, transparently and defensibly."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import services.governance.seasonal_arrears as A
from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/arrears", tags=["Seasonal-arrears overlay"])

_TEMPLATE = ("loan_ref,borrower_name,crop,region,country,exposure,currency,days_past_due,as_of_date\n"
             "L-1001,Green Valley Farms,wheat,Castilla,ES,4200000,EUR,45,2026-06-30\n"
             "L-1002,Rio Verde Cooperative,soy,Mato Grosso,BR,9800000,BRL,60,2026-06-30\n")


class RowsBody(BaseModel):
    rows: list[dict]
    currency: Optional[str] = Field(None, description="ISO 4217 code of the exposures, unless each row has a 'currency'.")
    book_date: Optional[str] = Field(None, description="YYYY-MM-DD the figures describe, unless each row has 'as_of_date'.")


@router.get("/template.csv", summary="Arrears upload template (CSV)")
def template():
    return Response(_TEMPLATE, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tellumen_arrears_template.csv"})


@router.get("/assessment", summary="Seasonal vs genuine classification of the past-due book (latest batch)")
def assessment(session: DbSession, month: Optional[int] = None,
               ctx: dict = Depends(require_permission("reports.view"))):
    return A.assessment(session, ctx["org"]["org_id"], month)


@router.post("/upload", status_code=201, summary="Upload the agri book's days-past-due (CSV file)")
async def upload(session: DbSession, file: UploadFile = File(...), currency: Optional[str] = Form(None),
                 book_date: Optional[str] = Form(None), ctx: dict = Depends(require_permission("reports.publish"))):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        rows = list(csv.DictReader(io.StringIO(raw)))
    except Exception:
        raise HTTPException(422, {"error": "bad_csv", "message": "Could not parse the CSV."})
    res = A.ingest(session, ctx["org"]["org_id"], rows, ctx["user"]["id"], currency, book_date)
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows", "skipped": res["skipped"],
                                  "message": "No usable rows. " + (res["skipped"][0]["reason"] if res["skipped"] else "")})
    return res


@router.post("/rows", status_code=201, summary="Upload arrears as JSON rows")
def upload_rows(body: RowsBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    res = A.ingest(session, ctx["org"]["org_id"], body.rows, ctx["user"]["id"], body.currency, body.book_date)
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows", "skipped": res["skipped"],
                                  "message": "No usable rows. " + (res["skipped"][0]["reason"] if res["skipped"] else "")})
    return res
