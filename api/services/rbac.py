"""
RBAC data access: authenticate a user, load their full context (org + roles +
permissions + entitlements), and write audit rows.

Raw SQL via text() — matches the style of api/auth.py and api/routers/bank.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.security import verify_password

_LOCKOUT_THRESHOLD = 5
_LOCKOUT_MINUTES = 15


class AuthError(Exception):
    """A non-credential authentication failure the login endpoint should surface specifically."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def authenticate(session: Session, email: str, password: str) -> Optional[dict]:
    """Validated user mapping on success; None on bad credentials. Raises AuthError for account-locked or
    SSO-enforced (password sign-in disabled). Tracks failed attempts and applies a temporary lockout."""
    from datetime import timedelta
    row = session.execute(text("""
        SELECT u.user_id, u.org_id, u.email, u.full_name, u.hashed_password, u.status,
               u.mfa_secret, u.mfa_enrolled_at, u.token_version, u.failed_login_count, u.locked_until,
               COALESCE(c.password_login_disabled, false) AS password_login_disabled
        FROM   users u
        LEFT JOIN tenant_sso_config c ON c.org_id = u.org_id
        WHERE  lower(u.email) = lower(:email)
    """), {"email": email}).mappings().first()

    if not row or row["status"] != "active":
        return None
    now = datetime.now(timezone.utc)
    if row["locked_until"] and row["locked_until"] > now:
        raise AuthError("account_locked", "Too many failed attempts. Try again later or reset your password.")
    if row["password_login_disabled"]:
        raise AuthError("sso_required", "Password sign-in is disabled for your organization. Use single sign-on.")

    if not verify_password(password, row["hashed_password"]):
        n = (row["failed_login_count"] or 0) + 1
        lock = now + timedelta(minutes=_LOCKOUT_MINUTES) if n >= _LOCKOUT_THRESHOLD else None
        session.execute(text("UPDATE users SET failed_login_count = :n, locked_until = :lk WHERE user_id = :uid"),
                        {"n": n, "lk": lock, "uid": str(row["user_id"])})
        session.commit()
        if lock:
            raise AuthError("account_locked", "Too many failed attempts. Your account is temporarily locked.")
        return None

    session.execute(text("UPDATE users SET last_login_at = :now, failed_login_count = 0, locked_until = NULL WHERE user_id = :uid"),
                    {"now": now, "uid": str(row["user_id"])})
    return dict(row)


def load_user_context(session: Session, user_id: str) -> Optional[dict]:
    """
    Full context for a user, reused by login and /me:
      {user:{id,email,full_name,status}, org:{org_id,name,type,country},
       roles:[names], permissions:[codes], entitlements:[offering_ids]}
    """
    u = session.execute(text("""
        SELECT u.user_id, u.email, u.full_name, u.status, u.token_version,
               o.org_id, o.name AS org_name, o.type AS org_type, o.country AS org_country
        FROM   users u
        JOIN   organizations o ON o.org_id = u.org_id
        WHERE  u.user_id = :uid
    """), {"uid": str(user_id)}).mappings().first()
    if not u:
        return None

    roles = session.execute(text("""
        SELECT r.name FROM user_roles ur
        JOIN   roles r ON r.role_id = ur.role_id
        WHERE  ur.user_id = :uid
        ORDER  BY r.name
    """), {"uid": str(user_id)}).scalars().all()

    permissions = session.execute(text("""
        SELECT DISTINCT p.code
        FROM   user_roles ur
        JOIN   role_permissions rp ON rp.role_id = ur.role_id
        JOIN   permissions p       ON p.permission_id = rp.permission_id
        WHERE  ur.user_id = :uid
        ORDER  BY p.code
    """), {"uid": str(user_id)}).scalars().all()

    entitlements = session.execute(text("""
        SELECT offering_id FROM org_entitlements
        WHERE  org_id = :oid AND enabled = true
        ORDER  BY offering_id
    """), {"oid": str(u["org_id"])}).scalars().all()

    return {
        "user": {
            "id": str(u["user_id"]),
            "email": u["email"],
            "full_name": u["full_name"],
            "status": u["status"],
            "token_version": u["token_version"] or 0,
        },
        "org": {
            "org_id": str(u["org_id"]),
            "name": u["org_name"],
            "type": u["org_type"],
            "country": u["org_country"],
        },
        "roles": list(roles),
        "permissions": list(permissions),
        "entitlements": list(entitlements),
    }


def write_audit(
    session: Session,
    *,
    org_id: Optional[str],
    actor_user_id: Optional[str],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    detail: Optional[dict] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    session.execute(text("""
        INSERT INTO access_audit_log
            (org_id, actor_user_id, action, target_type, target_id, detail, ip, user_agent)
        VALUES
            (:org_id, :actor, :action, :ttype, :tid, CAST(:detail AS jsonb), :ip, :ua)
    """), {
        "org_id": org_id,
        "actor": actor_user_id,
        "action": action,
        "ttype": target_type,
        "tid": target_id,
        "detail": json.dumps(detail) if detail is not None else None,
        "ip": ip,
        "ua": user_agent,
    })
