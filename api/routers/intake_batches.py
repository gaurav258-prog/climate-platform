"""The intake ledger — every customer data batch: what arrived, how it was secured and checked, what state it is in,
and its full history. Batches are written by the sector upload / push routes (services/intake/pipeline.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import CurrentUser, DbSession, require_permission

router = APIRouter(prefix="/v1/intake", tags=["Integration"])


@router.get("/batches", summary="Your data batches — what arrived, how it was checked, where it stands")
def list_batches(session: DbSession, ctx: CurrentUser, limit: int = Query(50, ge=1, le=200)):
    from services.intake.pipeline import list_batches as _list
    return {"batches": _list(session, ctx["org"]["org_id"], limit)}


@router.get("/batches/{batch_id}", summary="One batch: file, security result, every check, and its state history")
def get_batch(batch_id: str, session: DbSession, ctx: CurrentUser):
    from services.intake.pipeline import get_batch as _get
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
