"""The intake ledger — every customer data batch that reached the gate: what arrived, what the controls found,
who signed off. Read-only; the batches themselves are written by the sector upload / push routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.deps import CurrentUser, DbSession

router = APIRouter(prefix="/v1/intake", tags=["Integration"])


@router.get("/batches", summary="Your data batches — what arrived, how it was checked, who signed off")
def list_batches(session: DbSession, ctx: CurrentUser, limit: int = Query(50, ge=1, le=200)):
    from services.ingest.batches import list_batches as _list
    return {"batches": _list(session, ctx["org"]["org_id"], limit)}


@router.get("/batches/{batch_id}", summary="One batch with its full control report")
def get_batch(batch_id: str, session: DbSession, ctx: CurrentUser):
    from services.ingest.batches import get_batch as _get
    try:
        b = _get(session, ctx["org"]["org_id"], batch_id)
    except Exception:   # a malformed id
        raise HTTPException(404, {"error": "not_found", "message": "Batch not found."})
    if not b:
        raise HTTPException(404, {"error": "not_found", "message": "Batch not found."})
    return b
