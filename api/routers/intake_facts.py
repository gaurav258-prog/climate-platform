"""Asset facts per source and the differences between the client's values and ours (intake phase 3).

GET  /v1/intake/conflicts                       where the client's value and ours differ (open or resolved)
POST /v1/intake/conflicts/{id}/resolve          keep the client's / explain / use ours (a second person approves)
GET  /v1/intake/facts/{table}/{asset_id}        every fact of one asset: the client's, ours, the live value, history
POST /v1/intake/facts/sync                      record and reconcile the organisation's books now (hourly otherwise)
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import CurrentUser, DbSession, require_permission

router = APIRouter(prefix="/v1/intake", tags=["Integration"])


@router.get("/conflicts", summary="Where the client's value and Tellumen's differ")
def conflicts(session: DbSession, ctx: CurrentUser, status: Literal["open", "resolved"] = Query("open")):
    from services.intake.conflicts import list_conflicts
    return list_conflicts(session, ctx["org"]["org_id"], status)


class ResolveIn(BaseModel):
    decision: Literal["client", "tellumen", "explained"]
    note: Optional[str] = Field(None, max_length=1000)


@router.post("/conflicts/{conflict_id}/resolve", summary="Keep the client's value, explain the difference, or use ours")
def resolve(conflict_id: str, body: ResolveIn, session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.intake.conflicts import ConflictError
    from services.intake.conflicts import resolve as _resolve
    try:
        out = _resolve(session, ctx["org"]["org_id"], conflict_id, body.decision, ctx["user"]["id"], body.note)
    except ConflictError as e:
        raise HTTPException(409, {"error": "conflict", "message": str(e)})
    session.commit()
    return out


@router.get("/facts/{table}/{asset_id}", summary="Every fact of one asset, per source, with history")
def facts(table: str, asset_id: str, session: DbSession, ctx: CurrentUser):
    from services.intake.facts import asset_facts
    try:
        return asset_facts(session, ctx["org"]["org_id"], table, asset_id)
    except ValueError as e:
        raise HTTPException(404, {"error": "not_found", "message": str(e)})


@router.post("/facts/sync", summary="Record and reconcile this organisation's asset facts now")
def sync(session: DbSession, ctx: dict = Depends(require_permission("approvals.create"))):
    from services.intake.observations import sync as _sync
    out = _sync(session, ctx["org"]["org_id"])
    session.commit()
    return out
