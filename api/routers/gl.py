"""General-ledger reconciliation — upload GL control-account balances and tie the reported book total back to
the ledger (gate 4). CSV in; a reconciliation with an honest variance and tolerance out."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from api.deps import DbSession, require_permission
import services.governance.gl_recon as G

router = APIRouter(prefix="/v1/gl", tags=["General-ledger reconciliation"])

_TEMPLATE = ("account_code,account_name,balance_eur,control_for,as_of_date\n"
             "1000,Loans and advances to customers,3662900000,book,2026-06-30\n")


class RowsBody(BaseModel):
    rows: list[dict]


@router.get("/template.csv", summary="GL upload template (CSV)")
def template():
    return Response(_TEMPLATE, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tellumen_gl_template.csv"})


@router.get("/reconciliation", summary="Reconcile the reported book total to the GL (latest batch)")
def reconciliation(session: DbSession, ctx: dict = Depends(require_permission("reports.view"))):
    return G.reconciliation(session, ctx["org"]["org_id"], ctx["org"]["type"])


@router.post("/upload", status_code=201, summary="Upload GL control-account balances (CSV file)")
async def upload(session: DbSession, file: UploadFile = File(...),
                 ctx: dict = Depends(require_permission("reports.publish"))):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        rows = list(csv.DictReader(io.StringIO(raw)))
    except Exception:
        raise HTTPException(422, {"error": "bad_csv", "message": "Could not parse the CSV."})
    if not rows:
        raise HTTPException(422, {"error": "empty", "message": "No rows found. Use the template columns."})
    res = G.ingest(session, ctx["org"]["org_id"], rows, ctx["user"]["id"])
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows",
                                  "message": "No valid rows — each needs an account_code and a numeric balance_eur."})
    return res


@router.post("/rows", status_code=201, summary="Upload GL balances as JSON rows")
def upload_rows(body: RowsBody, session: DbSession, ctx: dict = Depends(require_permission("reports.publish"))):
    res = G.ingest(session, ctx["org"]["org_id"], body.rows, ctx["user"]["id"])
    if res["rows"] == 0:
        raise HTTPException(422, {"error": "no_valid_rows", "message": "No valid rows."})
    return res
