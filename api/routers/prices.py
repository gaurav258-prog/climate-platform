"""Commodity & farm-input price indices — load observed authoritative agency series and see the input-cost
pressure they put on the sourcing book. Not a forecast; observed market data weighted by the book's spend."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

import services.intelligence.price_index as P
from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/prices", tags=["Commodity price indices"])

_TEMPLATE = ("source,commodity,period_ym,index_value,unit\n"
             "FAO_FPI,coffee,2026-06,128.4,index 2014-16=100\n")


class RowsBody(BaseModel):
    rows: list[dict]


@router.get("/template.csv", summary="Price-index upload template (CSV)")
def template():
    return Response(_TEMPLATE, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tellumen_price_index_template.csv"})


@router.get("/pressure", summary="Input-cost pressure on the sourcing book from observed price moves")
def pressure(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return P.book_price_pressure(session, ctx["org"]["org_id"])


@router.post("/upload", status_code=201, summary="Load commodity price-index series (CSV file)")
async def upload(session: DbSession, file: UploadFile = File(...),
                 ctx: dict = Depends(require_permission("reports.publish"))):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        rows = list(csv.DictReader(io.StringIO(raw)))
    except Exception:
        raise HTTPException(422, {"error": "bad_csv", "message": "Could not parse the CSV."})
    res = P.ingest(session, rows)
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows",
                                  "message": "No valid rows — each needs commodity, period_ym (YYYY-MM) and index_value."})
    return res


@router.post("/rows", status_code=201, summary="Load price-index series as JSON rows")
def upload_rows(body: RowsBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    res = P.ingest(session, body.rows)
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows", "message": "No valid rows."})
    return res
