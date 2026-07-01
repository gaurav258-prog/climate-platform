"""
Admin endpoints — user management, role/permission matrix, audit trail.

Every endpoint is guarded by a specific permission; every mutation writes an
access_audit_log row. All data is scoped to the caller's organization.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, Pagination, require_permission
from api.security import hash_password
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


# ── Users ──────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email:     str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(..., min_length=1, max_length=255)
    password:  str = Field(..., min_length=6, max_length=200)
    role_ids:  list[str] = Field(default_factory=list)


class UserPatch(BaseModel):
    full_name: Optional[str] = None
    status:    Optional[str] = Field(None, pattern="^(active|disabled)$")
    password:  Optional[str] = Field(None, min_length=6, max_length=200)
    role_ids:  Optional[list[str]] = None


def _list_users(session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT u.user_id, u.email, u.full_name, u.status, u.last_login_at, u.created_at,
               COALESCE(array_agg(r.name) FILTER (WHERE r.name IS NOT NULL), '{}') AS roles
        FROM   users u
        LEFT   JOIN user_roles ur ON ur.user_id = u.user_id
        LEFT   JOIN roles r       ON r.role_id = ur.role_id
        WHERE  u.org_id = :o
        GROUP  BY u.user_id
        ORDER  BY u.created_at
    """), {"o": org_id}).mappings().all()
    return [{
        "id": str(r["user_id"]), "email": r["email"], "full_name": r["full_name"],
        "status": r["status"],
        "last_login_at": r["last_login_at"].isoformat() if r["last_login_at"] else None,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "roles": list(r["roles"]),
    } for r in rows]


def _valid_role_ids(session, org_id: str, role_ids: list[str]) -> list[str]:
    if not role_ids:
        return []
    rows = session.execute(text("""
        SELECT role_id FROM roles WHERE org_id = :o AND role_id = ANY(:ids)
    """), {"o": org_id, "ids": role_ids}).scalars().all()
    return [str(x) for x in rows]


@router.get("/users", summary="List users in your organization")
def list_users(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    return _list_users(session, ctx["org"]["org_id"])


@router.post("/users", status_code=201, summary="Create a user")
def create_user(body: UserCreate, session: DbSession,
                ctx: dict = Depends(require_permission("admin.users.manage"))):
    org_id = ctx["org"]["org_id"]
    exists = session.execute(text(
        "SELECT 1 FROM users WHERE org_id = :o AND lower(email) = lower(:e)"
    ), {"o": org_id, "e": body.email}).first()
    if exists:
        raise HTTPException(409, {"error": "email_taken", "message": "A user with that email already exists."})

    role_ids = _valid_role_ids(session, org_id, body.role_ids)
    primary_role = session.execute(text(
        "SELECT name FROM roles WHERE role_id = :r"
    ), {"r": role_ids[0]}).scalar() if role_ids else "viewer"

    uid = session.execute(text("""
        INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
        VALUES (gen_random_uuid(), :o, :e, :r, :fn, :hp, 'active', now())
        RETURNING user_id
    """), {"o": org_id, "e": body.email, "r": primary_role, "fn": body.full_name,
           "hp": hash_password(body.password)}).scalar()

    for rid in role_ids:
        session.execute(text(
            "INSERT INTO user_roles (user_id, role_id, granted_by) VALUES (:u, :r, :by) ON CONFLICT DO NOTHING"
        ), {"u": str(uid), "r": rid, "by": ctx["user"]["id"]})

    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="user.create",
                target_type="user", target_id=str(uid),
                detail={"email": body.email, "roles": role_ids})
    return {"id": str(uid), "email": body.email}


@router.patch("/users/{user_id}", summary="Update a user")
def patch_user(user_id: str, body: UserPatch, session: DbSession,
               ctx: dict = Depends(require_permission("admin.users.manage"))):
    org_id = ctx["org"]["org_id"]
    before = session.execute(text(
        "SELECT full_name, status FROM users WHERE user_id = :u AND org_id = :o"
    ), {"u": user_id, "o": org_id}).mappings().first()
    if not before:
        raise HTTPException(404, {"error": "not_found", "message": "User not found in your organization."})

    if body.full_name is not None:
        session.execute(text("UPDATE users SET full_name = :v WHERE user_id = :u"),
                        {"v": body.full_name, "u": user_id})
    if body.status is not None:
        session.execute(text("UPDATE users SET status = :v WHERE user_id = :u"),
                        {"v": body.status, "u": user_id})
    if body.password:
        session.execute(text("UPDATE users SET hashed_password = :v WHERE user_id = :u"),
                        {"v": hash_password(body.password), "u": user_id})
    if body.role_ids is not None:
        role_ids = _valid_role_ids(session, org_id, body.role_ids)
        session.execute(text("DELETE FROM user_roles WHERE user_id = :u"), {"u": user_id})
        for rid in role_ids:
            session.execute(text(
                "INSERT INTO user_roles (user_id, role_id, granted_by) VALUES (:u, :r, :by)"
            ), {"u": user_id, "r": rid, "by": ctx["user"]["id"]})

    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="user.update",
                target_type="user", target_id=user_id,
                detail={"before": dict(before),
                        "changed": body.model_dump(exclude_none=True, exclude={"password"})})
    return {"id": user_id, "updated": True}


# ── Roles & permission matrix ──────────────────────────────────────────

class RolePermsPatch(BaseModel):
    permission_codes: list[str]


@router.get("/roles", summary="Roles in your organization with their permissions")
def list_roles(session: DbSession, ctx: dict = Depends(require_permission("admin.roles.manage"))):
    rows = session.execute(text("""
        SELECT r.role_id, r.name, r.description, r.is_system,
               COALESCE(array_agg(p.code) FILTER (WHERE p.code IS NOT NULL), '{}') AS perms
        FROM   roles r
        LEFT   JOIN role_permissions rp ON rp.role_id = r.role_id
        LEFT   JOIN permissions p       ON p.permission_id = rp.permission_id
        WHERE  r.org_id = :o
        GROUP  BY r.role_id
        ORDER  BY r.name
    """), {"o": ctx["org"]["org_id"]}).mappings().all()
    return [{"id": str(r["role_id"]), "name": r["name"], "description": r["description"],
             "is_system": r["is_system"], "permissions": list(r["perms"])} for r in rows]


@router.get("/permissions", summary="Full permissions catalog")
def list_permissions(session: DbSession, ctx: dict = Depends(require_permission("admin.roles.manage"))):
    rows = session.execute(text(
        "SELECT code, description FROM permissions ORDER BY code"
    )).mappings().all()
    return [{"code": r["code"], "description": r["description"]} for r in rows]


@router.patch("/roles/{role_id}/permissions", summary="Replace a role's permissions")
def set_role_permissions(role_id: str, body: RolePermsPatch, session: DbSession,
                         ctx: dict = Depends(require_permission("admin.roles.manage"))):
    org_id = ctx["org"]["org_id"]
    role = session.execute(text(
        "SELECT name FROM roles WHERE role_id = :r AND org_id = :o"
    ), {"r": role_id, "o": org_id}).scalar()
    if not role:
        raise HTTPException(404, {"error": "not_found", "message": "Role not found in your organization."})

    session.execute(text("DELETE FROM role_permissions WHERE role_id = :r"), {"r": role_id})
    for code in body.permission_codes:
        session.execute(text("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT :r, permission_id FROM permissions WHERE code = :c
            ON CONFLICT DO NOTHING
        """), {"r": role_id, "c": code})

    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="role_permission.update",
                target_type="role", target_id=role_id,
                detail={"role": role, "permissions": body.permission_codes})
    return {"id": role_id, "permissions": body.permission_codes}


# ── Audit trail ────────────────────────────────────────────────────────

@router.get("/audit", summary="Access & change audit trail")
def audit(session: DbSession, page: Pagination,
          actor: Optional[str] = Query(None), action: Optional[str] = Query(None),
          ctx: dict = Depends(require_permission("admin.audit.view"))):
    rows = session.execute(text("""
        SELECT a.audit_id, a.action, a.target_type, a.target_id, a.detail, a.created_at,
               u.email AS actor_email, u.full_name AS actor_name
        FROM   access_audit_log a
        LEFT   JOIN users u ON u.user_id = a.actor_user_id
        WHERE  a.org_id = :o
          AND  (CAST(:actor AS text) IS NULL OR u.email ILIKE '%' || :actor || '%')
          AND  (CAST(:action AS text) IS NULL OR a.action = :action)
        ORDER  BY a.created_at DESC
        LIMIT :lim OFFSET :off
    """), {"o": ctx["org"]["org_id"], "actor": actor, "action": action,
           "lim": page["limit"], "off": page["offset"]}).mappings().all()
    return [{
        "id": str(r["audit_id"]), "action": r["action"],
        "target_type": r["target_type"], "target_id": r["target_id"],
        "detail": r["detail"],
        "actor_email": r["actor_email"], "actor_name": r["actor_name"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows]
