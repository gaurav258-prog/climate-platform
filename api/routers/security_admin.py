"""Administrative security actions: reset a user's MFA, and flush the email outbox.

Small, high-privilege operations kept out of the large admin router. MFA reset is a help-desk recovery for a
tenant admin; the email drain lets a platform operator deliver queued invites/resets when a worker isn't running.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import DbSession, require_permission
from services.governance import account_security as acct

router = APIRouter(prefix="/v1/security", tags=["security"])


@router.post("/users/{user_id}/reset-mfa", summary="Clear a user's MFA so they re-enrol")
def reset_mfa(user_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    try:
        return acct.admin_reset_mfa(session, actor_user_id=ctx["user"]["id"], org_id=ctx["org"]["org_id"], user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"message": str(e)})


@router.post("/email/drain", summary="Deliver pending emails from the outbox")
def drain_email(session: DbSession, ctx: dict = Depends(require_permission("platform.admin")), limit: int = 100):
    from services.notifications.mailer import deliver
    return deliver(session, limit=limit)
