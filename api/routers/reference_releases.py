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


@router.get("", summary="Reviewed yield-source releases — staged, proposed, landed, rejected — and each source's feed")
def list_releases(session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.data.feeds import feed_freshness
    from services.reference.yield_sources import all_sources
    fresh = {f["key"]: f for f in feed_freshness(session)}
    feeds = [{"source": ys.key, "label": ys.label(),
              **{k: fresh[ys.feed_key].get(k) for k in ("name", "cadence_days", "last_refresh", "last_status", "status",
                                                        "awaiting_review", "attribution", "note")}}
             for ys in all_sources()]
    return {"feeds": feeds, "releases": R.releases(session)}


class Approvers(BaseModel):
    action_key: str = Field(..., max_length=60)
    human_approvers: int
    reason: str = Field(..., max_length=2000)


@router.get("/policy", summary="How many people must approve a platform change (E150)")
def get_policy(session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.governance.platform_policy import policies
    return {"policies": policies(session)}


@router.put("/policy", summary="State how many people approve (1: the system proposes, one person approves; 2: four eyes)")
def put_policy(body: Approvers, session: DbSession, ctx: dict = Depends(_REVIEW)):
    from services.governance.platform_policy import PolicyError, set_human_approvers
    try:
        return set_human_approvers(session, body.action_key, body.human_approvers, ctx["user"]["id"], body.reason)
    except PolicyError as e:
        raise HTTPException(422, {"error": "policy", "message": str(e)}) from e


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


@router.post("/check", summary="Check a yield source for new data now (stages it for review; nothing lands)")
def check_now(session: DbSession, source: str = Query("faostat"), ctx: dict = Depends(_REVIEW)):
    from services.data.feeds import refresh_one
    from services.reference.yield_sources import get
    try:
        ys = get(source)
    except KeyError as e:
        raise HTTPException(422, {"error": "release", "message": str(e)}) from e
    out = refresh_one(session, ys.feed_key, actor_user_id=ctx["user"]["id"])
    return {**out, "awaiting_review": R.pending(session, ys)}


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
