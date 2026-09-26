"""The intake ledger — every customer data batch: what arrived, how it was secured and checked, what state it is in,
and its full history. Batches are written by the sector upload / push routes (services/intake/pipeline.py)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DbSession, require_permission

router = APIRouter(prefix="/v1/intake", tags=["Integration"])


@router.get("/batches", summary="Your data batches — what arrived, how it was checked, where it stands")
def list_batches(session: DbSession, ctx: CurrentUser, limit: int = Query(50, ge=1, le=200)):
    from services.intake.ledger import list_batches as _list
    return {"batches": _list(session, ctx["org"]["org_id"], limit)}


@router.get("/batches/{batch_id}", summary="One batch: file, security result, every check, and its state history")
def get_batch(batch_id: str, session: DbSession, ctx: CurrentUser):
    from services.intake.ledger import get_batch as _get
    try:
        b = _get(session, ctx["org"]["org_id"], batch_id)
    except Exception:   # a malformed id
        b = None
    if not b:
        raise HTTPException(404, {"error": "not_found", "message": "Batch not found."})
    return b


@router.post("/batches/{batch_id}/rescan", summary="Retry the malware scan on a held batch and continue if it passes")
def rescan(batch_id: str, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.intake.pipeline import IntakeError, resume_held
    try:
        return resume_held(session, ctx["org"]["org_id"], batch_id, ctx["user"]["id"])
    except IntakeError as e:
        raise HTTPException(e.status, e.body) from e


# ── column mappings: how one of your sources maps onto our template (versioned; every batch pins the version it used) ──

def _template_or_404(template: str):
    from services.intake.catalog import TEMPLATES
    if template not in TEMPLATES:
        raise HTTPException(404, {"error": "unknown_template", "message": f"No template '{template}'."})
    return TEMPLATES[template]


@router.get("/templates/{template}/fields", summary="The fields of one template — what a mapping maps onto")
def template_fields(template: str, ctx: CurrentUser):
    from services.intake.catalog import template_fields as _fields
    _template_or_404(template)
    return {"template": template, "fields": _fields(template)}


@router.post("/templates/{template}/inspect", summary="Read a file's columns and propose how they map — nothing is saved")
async def inspect_file(template: str, session: DbSession, ctx: CurrentUser, file: UploadFile = File(...)):
    """Security-inspects and reads the file (CSV or Excel), then proposes which of your columns feeds each field —
    from the column names and the values, with a confidence and the reasons — and any mapping you already confirmed
    for this exact layout. You confirm or correct it in the mapping editor."""
    from services.intake.inspect import inspect
    from services.intake.pipeline import IntakeError
    _template_or_404(template)
    try:
        return inspect(session, ctx["org"]["org_id"], template, await file.read(), file.filename)
    except IntakeError as e:
        raise HTTPException(e.status, e.body) from e


@router.get("/mappings", summary="Your saved column mappings (latest version of each)")
def list_mappings(session: DbSession, ctx: CurrentUser, template: Optional[str] = Query(None)):
    from services.intake.mapping import latest
    return {"mappings": latest(session, ctx["org"]["org_id"], template)}


class MappingIn(BaseModel):
    template: str
    name: str = Field(..., min_length=1, max_length=80, description="Usually the source system, e.g. 'Core banking'.")
    column_map: dict[str, Optional[str]] = Field(..., description="Our field → your column name.")
    source_columns: Optional[list[str]] = Field(None, description="The file's column names — lets the next file with the "
                                                                 "same layout use this mapping automatically.")
    transforms: dict[str, dict] = Field(default_factory=dict,
                                        description='Per field: {"multiply": 1000} | {"currency": "USD"} | '
                                                    '{"currency_column": "Ccy"} | {"values": {"Concrete": "fire_resistive"}}')


@router.post("/mappings", status_code=201, summary="Save a column mapping (saving an existing name makes a new version)")
def save_mapping(body: MappingIn, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.intake.catalog import template_fields as _fields
    from services.intake.mapping import MappingError, save
    _template_or_404(body.template)
    try:
        out = save(session, ctx["org"]["org_id"], body.template, body.name, {k: v for k, v in body.column_map.items() if v},
                   body.transforms, ctx["user"]["id"], _fields(body.template), body.source_columns)
    except MappingError as e:
        raise HTTPException(400, {"error": "bad_mapping", "message": str(e)}) from e
    session.commit()
    return out


# ── drop-folder channels: where an SFTP feed lands, one per template; each file runs through the intake pipeline ──

class ChannelIn(BaseModel):
    template: str
    owner_user_id: str = Field(..., description="Stands as the sender: a batch with a failed check goes to a DIFFERENT person.")
    mapping_profile_id: Optional[str] = Field(None, description="Optional pinned mapping; otherwise your confirmed layout is used.")


@router.get("/channels", summary="Your drop-folder channels (where your SFTP feed lands)")
def list_channels(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.intake.dropfolder import list_channels as _list
    return {"channels": _list(session, ctx["org"]["org_id"])}


@router.post("/channels", status_code=201, summary="Open a drop folder for one of your templates")
def create_channel(body: ChannelIn, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.intake.dropfolder import ChannelError
    from services.intake.dropfolder import create_channel as _create
    try:
        out = _create(session, ctx["org"]["org_id"], body.template, body.owner_user_id, ctx["user"]["id"], body.mapping_profile_id)
    except ChannelError as e:
        raise HTTPException(400, {"error": "bad_channel", "message": str(e)}) from e
    session.commit()
    return out


@router.post("/channels/{channel_id}/sweep", summary="Pick up the files waiting in a drop folder now")
def sweep_channel(channel_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.intake.dropfolder import get_channel
    from services.intake.dropfolder import sweep_channel as _sweep
    try:
        ch = get_channel(session, ctx["org"]["org_id"], channel_id)
    except Exception:   # a malformed id
        ch = None
    if not ch:
        raise HTTPException(404, {"error": "not_found", "message": "Channel not found."})
    session.rollback()   # the sweep uses its own transaction per file
    return {"channel_id": channel_id, "files": _sweep(ch, ctx["org"]["org_id"])}


# ── SFTP access keys for the drop folders (one login per organisation, keys only) ──

class SftpKeyIn(BaseModel):
    label: str = Field(..., min_length=1, max_length=80, description="Which system uses this key.")
    public_key: str = Field(..., min_length=20, max_length=4000, description="The OpenSSH public key line (never the private key).")


@router.get("/sftp-keys", summary="Public keys allowed to log in to your drop folders")
def list_sftp_keys(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.intake.sftp_keys import list_keys
    return {"keys": list_keys(session, ctx["org"]["org_id"])}


@router.post("/sftp-keys", status_code=201, summary="Register a public key for SFTP access")
def add_sftp_key(body: SftpKeyIn, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.intake.sftp_keys import SftpKeyError, add
    if "PRIVATE KEY" in body.public_key:
        raise HTTPException(400, {"error": "private_key", "message": "That is a PRIVATE key — never share it. Paste the .pub file's line."})
    try:
        out = add(session, ctx["org"]["org_id"], body.label, body.public_key, ctx["user"]["id"])
    except SftpKeyError as e:
        raise HTTPException(400, {"error": "bad_key", "message": str(e)}) from e
    session.commit()
    return out


@router.delete("/sftp-keys/{key_id}", summary="Revoke an SFTP key (it stops working at the next login)")
def revoke_sftp_key(key_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    from services.intake.sftp_keys import revoke
    try:
        ok = revoke(session, ctx["org"]["org_id"], key_id, ctx["user"]["id"])
    except Exception:   # a malformed id
        ok = False
    if not ok:
        raise HTTPException(404, {"error": "not_found", "message": "Active key not found."})
    session.commit()
    return {"key_id": key_id, "revoked": True}


# ── currency coverage (the FX foundation: which official source serves each currency, how fresh, how well sources agree) ──

@router.get("/fx/coverage", summary="Every currency: which source converts it today, how fresh, and source agreement")
def fx_coverage(session: DbSession, ctx: CurrentUser, on: Optional[str] = Query(None, description="Book date YYYY-MM-DD (default today)")):
    from datetime import date as _date

    from services.reference.fx import coverage
    try:
        d = _date.fromisoformat(on) if on else None
    except ValueError as e:
        raise HTTPException(400, {"error": "bad_date", "message": "Use YYYY-MM-DD."}) from e
    return coverage(session, d)
