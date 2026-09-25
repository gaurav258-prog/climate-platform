"""The intake ledger — every customer data batch: what arrived, how it was secured and checked, what state it is in,
and its full history. Batches are written by the sector upload / push routes (services/intake/pipeline.py)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.get("/mappings", summary="Your saved column mappings (latest version of each)")
def list_mappings(session: DbSession, ctx: CurrentUser, template: Optional[str] = Query(None)):
    from services.intake.mapping import latest
    return {"mappings": latest(session, ctx["org"]["org_id"], template)}


class MappingIn(BaseModel):
    template: str
    name: str = Field(..., min_length=1, max_length=80, description="Usually the source system, e.g. 'Core banking'.")
    column_map: dict[str, Optional[str]] = Field(..., description="Our field → your column name.")
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
                   body.transforms, ctx["user"]["id"], _fields(body.template))
    except MappingError as e:
        raise HTTPException(400, {"error": "bad_mapping", "message": str(e)}) from e
    session.commit()
    return out
