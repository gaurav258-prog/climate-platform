"""Reference data releases — the platform operators' review of a publisher file before it lands (E148).

FAOSTAT crop production is fetched on the feed schedule and STAGED with its difference against the store; here an
operator reads that difference, proposes landing it (an approval request the second operator decides through the one
approvals path, POST /v1/approvals/{id}/decide — the maker can never approve), or rejects a damaged file. Every route
needs reference.release_review, a platform-operator permission no customer role holds.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from services.reference import crop_releases as R

router = APIRouter(prefix="/v1/ops/reference-releases", tags=["Platform operator"])
_REVIEW = require_permission("reference.release_review")


class Reason(BaseModel):
    reason: str = Field(..., max_length=2000)


def _fail(e: R.ReleaseError) -> HTTPException:
    return HTTPException(404 if isinstance(e, R.ReleaseNotFound) else 409, {"error": "release", "message": str(e)})


@router.get("", summary="FAOSTAT releases — staged, proposed, landed, rejected — and the feed's state")
def list_releases(session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.data.feeds import feed_freshness
    feed = next(f for f in feed_freshness(session) if f["key"] == "crop_production_faostat")
    return {"feed": {k: feed.get(k) for k in ("name", "cadence_days", "last_refresh", "last_status", "status",
                                              "awaiting_review", "attribution", "note")},
            "releases": R.releases(session)}


@router.get("/{release_id}", summary="One release — its difference against the store, row by row (by change)")
def release_detail(release_id: UUID, session: DbSession, change: Optional[str] = Query(None),
                   ctx: dict = Depends(_REVIEW)):
    rel = next((r for r in R.releases(session, limit=1000) if r["release_id"] == str(release_id)), None)
    if rel is None:
        raise HTTPException(404, {"error": "release", "message": "release not found"})
    try:
        return {**rel, "rows": R.release_rows(session, str(release_id), change)}
    except R.ReleaseError as e:
        raise HTTPException(422, {"error": "release", "message": str(e)}) from e


@router.post("/check", summary="Check FAOSTAT for a new file now (stages it for review; nothing lands)")
def check_now(session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.data.feeds import refresh_one
    out = refresh_one(session, "crop_production_faostat", actor_user_id=ctx["user"]["id"])
    return {**out, "awaiting_review": R.pending(session)}


@router.post("/{release_id}/propose", summary="Propose landing a reviewed release (a second operator decides)")
def propose(release_id: UUID, body: Reason, session: DbSession, ctx: dict = Depends(_REVIEW)):
    try:
        out = R.propose(session, ctx["org"]["org_id"], str(release_id), ctx["user"]["id"], body.reason)
    except R.ReleaseError as e:
        raise _fail(e) from e
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="reference.release_proposed",
                target_type="crop_yield_release", target_id=str(release_id), detail={"review": body.reason.strip()})
    return out


@router.post("/{release_id}/reject", summary="Reject a staged release (nothing lands)")
def reject(release_id: UUID, body: Reason, session: DbSession, ctx: dict = Depends(_REVIEW)):
    try:
        out = R.reject(session, str(release_id), ctx["user"]["id"], body.reason)
    except R.ReleaseError as e:
        raise _fail(e) from e
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"], action="reference.release_rejected",
                target_type="crop_yield_release", target_id=str(release_id), detail={"reason": body.reason.strip()})
    return out
