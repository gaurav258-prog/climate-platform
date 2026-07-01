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


def authenticate(session: Session, email: str, password: str) -> Optional[dict]:
    """Return the user row (mapping) if email+password are valid and active, else None."""
    row = session.execute(text("""
        SELECT user_id, org_id, email, full_name, hashed_password, status
        FROM   users
        WHERE  lower(email) = lower(:email)
    """), {"email": email}).mappings().first()

    if not row or row["status"] != "active":
        return None
    if not verify_password(password, row["hashed_password"]):
        return None

    session.execute(
        text("UPDATE users SET last_login_at = :now WHERE user_id = :uid"),
        {"now": datetime.now(timezone.utc), "uid": str(row["user_id"])},
    )
    return dict(row)


def load_user_context(session: Session, user_id: str) -> Optional[dict]:
    """
    Full context for a user, reused by login and /me:
      {user:{id,email,full_name,status}, org:{org_id,name,type,country},
       roles:[names], permissions:[codes], entitlements:[offering_ids]}
    """
    u = session.execute(text("""
        SELECT u.user_id, u.email, u.full_name, u.status,
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
