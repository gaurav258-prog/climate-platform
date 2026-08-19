"""Seasonal-arrears overlay — upload the agri book's days-past-due and see which past-dues are normal
harvest-cycle carry-over vs genuine deterioration, transparently and defensibly."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import services.governance.seasonal_arrears as A
from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/arrears", tags=["Seasonal-arrears overlay"])

_TEMPLATE = ("loan_ref,borrower_name,crop,region,exposure_eur,days_past_due,as_of_date\n"
             "L-1001,Green Valley Farms,wheat,Castilla,4200000,45,2026-11-30\n")


class RowsBody(BaseModel):
    rows: list[dict]


@router.get("/template.csv", summary="Arrears upload template (CSV)")
def template():
    return Response(_TEMPLATE, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tellumen_arrears_template.csv"})


@router.get("/assessment", summary="Seasonal vs genuine classification of the past-due book (latest batch)")
def assessment(session: DbSession, month: Optional[int] = None,
               ctx: dict = Depends(require_permission("reports.view"))):
    return A.assessment(session, ctx["org"]["org_id"], month)


@router.post("/upload", status_code=201, summary="Upload the agri book's days-past-due (CSV file)")
async def upload(session: DbSession, file: UploadFile = File(...),
                 ctx: dict = Depends(require_permission("reports.publish"))):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        rows = list(csv.DictReader(io.StringIO(raw)))
    except Exception:
        raise HTTPException(422, {"error": "bad_csv", "message": "Could not parse the CSV."})
    res = A.ingest(session, ctx["org"]["org_id"], rows, ctx["user"]["id"])
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows",
                                  "message": "No valid rows — each needs a loan_ref and numeric days_past_due."})
    return res


@router.post("/rows", status_code=201, summary="Upload arrears as JSON rows")
def upload_rows(body: RowsBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    res = A.ingest(session, ctx["org"]["org_id"], body.rows, ctx["user"]["id"])
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows", "message": "No valid rows."})
    return res
