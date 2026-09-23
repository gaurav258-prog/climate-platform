"""Entity-structure import — the standard workflow for onboarding any institution's real org tree.

Replaces the one-off hand-written script this session used to mirror ING Bank N.V.
(scripts/seed_ing_org_structure.py) with a reusable, reviewed ingestion path: upload a CSV (or, once
ANTHROPIC_API_KEY is configured, a source document — see services/governance/entity_extraction.py, honestly
not built yet), review/correct the staged rows, then confirm to actually create them as reporting entities.
"""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

import services.governance.entity_structure_import as ESI
from api.deps import DbSession, require_permission
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/entity-structure", tags=["Entity-structure import"])

_TEMPLATE = ("entity_name,parent_entity_name,kind,country,ownership_pct,consolidation_method\n"
             "Acme Bank N.V.,,legal_entity,NL,100,full\n"
             "Acme Belgium N.V.,Acme Bank N.V.,legal_entity,BE,100,full\n"
             "Acme Poland S.A.,Acme Bank N.V.,legal_entity,PL,75,full\n"
             "Acme Associate Bank,Acme Bank N.V.,legal_entity,TH,23,equity\n"
             "Branch of Acme Bank N.V. — Spain,Acme Bank N.V.,branch,ES,100,full\n")


@router.get("/template.csv", summary="Entity-structure upload template (CSV)")
def template():
    return Response(_TEMPLATE, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tellumen_entity_structure_template.csv"})


@router.post("/imports", status_code=201, summary="Stage an org tree from a CSV (parent_entity_name resolves within the file)")
async def create_import(session: DbSession, file: UploadFile = File(...),
                        ctx: dict = Depends(require_permission("admin.users.manage"))):
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    try:
        csv_rows = list(csv.DictReader(io.StringIO(raw)))
    except Exception:
        raise HTTPException(422, {"error": "bad_csv", "message": "Could not parse the CSV."})
    if not csv_rows:
        raise HTTPException(422, {"error": "empty", "message": "No rows found. Use the template columns."})
    rows = [{"name": r.get("entity_name"), "parent_ref": r.get("parent_entity_name"), "kind": r.get("kind"),
            "country": r.get("country"),
            "ownership_pct": float(r["ownership_pct"]) if (r.get("ownership_pct") or "").strip() else None,
            "consolidation_method": r.get("consolidation_method"), "source_note": "customer-entered"}
           for r in csv_rows]
    try:
        imp = ESI.create_import(session, ctx["org"]["org_id"], ctx["user"]["id"], "manual_csv", rows,
                                source_document_name=file.filename)
    except ESI.ImportError_ as ex:
        raise HTTPException(422, {"error": "import_error", "message": str(ex)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="entity_structure.stage", target_type="entity_structure_import",
                target_id=imp["import_id"], detail={"source": "manual_csv", "n_rows": len(rows)})
    return imp


@router.post("/imports/extract", status_code=201, summary="Stage an org tree extracted from an uploaded document (not yet available)")
async def create_import_from_document(session: DbSession, file: UploadFile = File(...),
                                      ctx: dict = Depends(require_permission("admin.users.manage"))):
    import services.governance.entity_extraction as EX
    raw = await file.read()
    try:
        rows = EX.extract_from_document(raw, file.filename)
    except EX.ExtractionUnavailable as ex:
        raise HTTPException(503, {"error": "extraction_unavailable", "message": str(ex)})
    imp = ESI.create_import(session, ctx["org"]["org_id"], ctx["user"]["id"], "document_extraction", rows,
                            source_document_name=file.filename)
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="entity_structure.stage", target_type="entity_structure_import",
                target_id=imp["import_id"], detail={"source": "document_extraction", "n_rows": len(rows)})
    return imp


@router.get("/imports", summary="Every entity-structure import on record (newest first)")
def list_imports(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    return {"imports": ESI.list_imports(session, ctx["org"]["org_id"])}


@router.get("/imports/{import_id}", summary="One staged import — every row, for review before confirming")
def get_import(import_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    try:
        return ESI.get_import(session, ctx["org"]["org_id"], import_id)
    except ESI.ImportError_ as ex:
        raise HTTPException(404, {"error": "not_found", "message": str(ex)})


class RowPatch(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    kind: Optional[str] = Field(None, max_length=40)
    country: Optional[str] = Field(None, max_length=3)
    ownership_pct: Optional[float] = Field(None, ge=0, le=100)
    consolidation_method: Optional[str] = Field(None, max_length=20)
    parent_ref: Optional[str] = Field(None, max_length=200)
    parent_entity_id: Optional[str] = None
    status: Optional[str] = Field(None, max_length=20)   # 'proposed' | 'edited' | 'rejected'
    source_note: Optional[str] = Field(None, max_length=500)


@router.patch("/imports/{import_id}/rows/{row_id}", summary="Correct or reject one staged row before confirming")
def update_row(import_id: str, row_id: str, body: RowPatch, session: DbSession,
               ctx: dict = Depends(require_permission("admin.users.manage"))):
    kwargs = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return ESI.update_row(session, ctx["org"]["org_id"], import_id, row_id, **kwargs)
    except ESI.ImportError_ as ex:
        raise HTTPException(409, {"error": "import_error", "message": str(ex)})


@router.post("/imports/{import_id}/confirm", summary="Confirm the reviewed batch — creates real reporting entities")
def confirm_import(import_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    try:
        res = ESI.confirm_import(session, ctx["org"]["org_id"], import_id, ctx["user"]["id"])
    except ESI.ImportError_ as ex:
        raise HTTPException(409, {"error": "import_error", "message": str(ex)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="entity_structure.confirm", target_type="entity_structure_import",
                target_id=import_id, detail={"n_created": res["n_created"], "n_rejected": res["n_rejected"]})
    return res


@router.post("/imports/{import_id}/discard", summary="Discard a staged import without creating anything")
def discard_import(import_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    try:
        res = ESI.discard_import(session, ctx["org"]["org_id"], import_id)
    except ESI.ImportError_ as ex:
        raise HTTPException(409, {"error": "import_error", "message": str(ex)})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="entity_structure.discard", target_type="entity_structure_import", target_id=import_id, detail={})
    return res
