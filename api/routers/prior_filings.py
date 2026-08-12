"""Prior filings — bring in the ESG reports you have already filed and had accepted, so your reported
figures become part of your track record for trends and follow-up questions. Upload the submitted file
itself; Tellumen reads it into its reported lines for you to confirm."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import CurrentUser, DbSession, require_permission
import services.governance.prior_filings as PF

# original-file media types, by stored format
_MEDIA = {"pdf": "application/pdf", "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "xbrl": "application/xml", "ixbrl": "text/html"}

router = APIRouter(prefix="/v1/prior-filings", tags=["Prior filings"])

MAX_UPLOAD = 25 * 1024 * 1024  # 25 MB — a filed disclosure package


@router.get("/frameworks", summary="Frameworks you can bring a prior filing for")
def frameworks(ctx: CurrentUser, _p: dict = Depends(require_permission("reports.view"))):
    return {"frameworks": PF.frameworks_for(ctx["org"]["type"])}


@router.get("", summary="Your imported prior filings")
def list_filings(session: DbSession, ctx: CurrentUser, framework: Optional[str] = None,
                 _p: dict = Depends(require_permission("reports.view"))):
    return {"filings": PF.list_filings(session, ctx["org"]["org_id"], framework)}


# static /trends routes must come before the /{filing_id} catch-all, or 'trends' is read as an id
@router.get("/trends", summary="Your reported figures over time, with a projection from the last filed value")
def trends(session: DbSession, ctx: CurrentUser, framework: Optional[str] = None, horizon_years: int = 3,
           _p: dict = Depends(require_permission("reports.view"))):
    return PF.trends(session, ctx["org"]["org_id"], framework, horizon_years)


@router.get("/trend/{framework}/{datapoint_key}", summary="Your reported values for one datapoint over time")
def trend(framework: str, datapoint_key: str, session: DbSession, ctx: CurrentUser,
          _p: dict = Depends(require_permission("reports.view"))):
    return PF.trend(session, ctx["org"]["org_id"], framework, datapoint_key)


@router.get("/{filing_id}", summary="One imported filing with its reported lines")
def get_filing(filing_id: str, session: DbSession, ctx: CurrentUser,
               _p: dict = Depends(require_permission("reports.view"))):
    try:
        return PF.get_filing(session, filing_id, ctx["org"]["org_id"])
    except PF.FilingError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.get("/{filing_id}/file", summary="Download the original filed report, exactly as submitted")
def download_original(filing_id: str, session: DbSession, ctx: CurrentUser,
                      _p: dict = Depends(require_permission("reports.view"))):
    row = session.execute(text("""
        SELECT original_filename, file_format, file_bytes FROM reported_filing
        WHERE filing_id = :fid AND org_id = :org
    """), {"fid": filing_id, "org": ctx["org"]["org_id"]}).mappings().first()
    if not row:
        raise HTTPException(404, {"error": "not_found", "message": "Filing not found."})
    return Response(content=bytes(row["file_bytes"]),
                    media_type=_MEDIA.get(row["file_format"], "application/octet-stream"),
                    headers={"Content-Disposition": f'attachment; filename="{row["original_filename"]}"'})


@router.post("/upload", status_code=201, summary="Upload a filed report — read it into reported lines to confirm")
async def upload(session: DbSession, ctx: CurrentUser,
                 file: UploadFile = File(...),
                 framework: str = Form(...),
                 period_label: str = Form(...),
                 entity_name: Optional[str] = Form(None),
                 _p: dict = Depends(require_permission("reports.publish"))):
    data = await file.read()
    if not data:
        raise HTTPException(400, {"error": "empty", "message": "The uploaded file is empty."})
    if len(data) > MAX_UPLOAD:
        raise HTTPException(400, {"error": "too_large", "message": "File exceeds the 25 MB limit."})
    try:
        return PF.create_from_upload(session, ctx["org"]["org_id"], ctx["user"]["id"],
                                     framework=framework, period_label=period_label,
                                     entity_name=entity_name, filename=file.filename or "upload", data=data)
    except PF.FilingError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})


class ConfirmEdit(BaseModel):
    figure_id:     str
    value_num:     Optional[float] = None
    value_text:    Optional[str] = None
    datapoint_key: Optional[str] = None
    drop:          Optional[bool] = None


class ConfirmBody(BaseModel):
    edits:      Optional[list[ConfirmEdit]] = None
    basis_note: Optional[str] = None


@router.post("/{filing_id}/confirm", summary="Confirm the read figures and lock the filing")
def confirm(filing_id: str, body: ConfirmBody, session: DbSession, ctx: CurrentUser,
            _p: dict = Depends(require_permission("reports.publish"))):
    try:
        edits = [e.model_dump(exclude_none=True) for e in (body.edits or [])]
        return PF.confirm(session, filing_id, ctx["org"]["org_id"], ctx["user"]["id"],
                          edits=edits, basis_note=body.basis_note)
    except PF.FilingError as e:
        raise HTTPException(400, {"error": "bad_request", "message": str(e)})


@router.delete("/{filing_id}", status_code=204, summary="Remove an imported filing")
def delete_filing(filing_id: str, session: DbSession, ctx: CurrentUser,
                  _p: dict = Depends(require_permission("reports.publish"))):
    try:
        PF.delete_filing(session, filing_id, ctx["org"]["org_id"])
    except PF.FilingError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})
