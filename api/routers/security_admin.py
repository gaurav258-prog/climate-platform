"""Administrative security actions: reset a user's MFA, and flush the email outbox.

Small, high-privilege operations kept out of the large admin router. MFA reset is a help-desk recovery for a
tenant admin; the email drain lets a platform operator deliver queued invites/resets when a worker isn't running.
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from api.deps import DbSession, require_permission, require_step_up
from services.governance import account_security as acct

router = APIRouter(prefix="/v1/security", tags=["security"])


@router.post("/users/{user_id}/reset-mfa", summary="Clear a user's MFA so they re-enrol (requires step-up)")
def reset_mfa(user_id: str, session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage")),
              _su: dict = Depends(require_step_up)):
    try:
        return acct.admin_reset_mfa(session, actor_user_id=ctx["user"]["id"], org_id=ctx["org"]["org_id"], user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail={"message": str(e)})


@router.post("/email/drain", summary="Deliver pending emails from the outbox")
def drain_email(session: DbSession, ctx: dict = Depends(require_permission("platform.admin")), limit: int = 100):
    from services.notifications.mailer import deliver
    return deliver(session, limit=limit)


@router.post("/retention/cleanup", summary="Prune expired tokens, consumed challenges, delivered mail, aged audit")
def retention_cleanup(session: DbSession, ctx: dict = Depends(require_permission("platform.admin"))):
    from services.governance import retention
    return retention.cleanup(session)


@router.get("/access-review", summary="Access review — every user, their roles, MFA, and last activity")
def access_review(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    rows = session.execute(text("""
        SELECT u.user_id, u.email, u.full_name, u.status, u.auth_provider,
               (u.mfa_enrolled_at IS NOT NULL) AS mfa_enrolled, u.last_login_at,
               COALESCE(array_agg(r.name) FILTER (WHERE r.name IS NOT NULL), '{}') AS roles
        FROM users u
        LEFT JOIN user_roles ur ON ur.user_id = u.user_id
        LEFT JOIN roles r ON r.role_id = ur.role_id
        WHERE u.org_id = CAST(:o AS uuid)
        GROUP BY u.user_id ORDER BY u.email
    """), {"o": ctx["org"]["org_id"]}).mappings().all()
    return {"users": [dict(r) for r in rows]}


@router.get("/audit/export.csv", summary="Export this organization's audit log as CSV")
def audit_export(session: DbSession, ctx: dict = Depends(require_permission("admin.audit.view")), limit: int = 10000):
    rows = session.execute(text("""
        SELECT created_at, actor_user_id, action, target_type, target_id, ip, user_agent
        FROM access_audit_log WHERE org_id = CAST(:o AS uuid)
        ORDER BY created_at DESC LIMIT :lim
    """), {"o": ctx["org"]["org_id"], "lim": limit}).mappings().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "actor_user_id", "action", "target_type", "target_id", "ip", "user_agent"])
    for r in rows:
        w.writerow([r["created_at"], r["actor_user_id"], r["action"], r["target_type"], r["target_id"], r["ip"], r["user_agent"]])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=audit-log.csv"})
