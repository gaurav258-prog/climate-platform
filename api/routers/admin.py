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


# ── Approval matrix ────────────────────────────────────────────────────

_POLICY_LABELS = {
    "supply.site.update": "Edit an operational site",
    "supply.site.delete": "Delete an operational site",
    "supply.plot.update": "Edit a sourcing plot",
    "supply.plot.delete": "Delete a sourcing plot",
}


class PolicyPatch(BaseModel):
    action_key:        str = Field(..., min_length=1, max_length=80)
    requires_approval: bool
    material_fields:   Optional[list[str]] = None


@router.get("/approval-policy", summary="The approval matrix — which actions need 4-eyes (org rules over platform defaults)")
def get_approval_policy(session: DbSession, ctx: dict = Depends(require_permission("admin.approval_policy.manage"))):
    org_id = ctx["org"]["org_id"]
    rows = session.execute(text("""
        SELECT DISTINCT ON (action_key) action_key, requires_approval, material_fields,
               (org_id IS NOT NULL) AS org_override
        FROM   approval_policy
        WHERE  org_id = :o OR org_id IS NULL
        ORDER  BY action_key, org_id NULLS LAST
    """), {"o": org_id}).mappings().all()
    return [{
        "action_key": r["action_key"], "label": _POLICY_LABELS.get(r["action_key"], r["action_key"]),
        "requires_approval": bool(r["requires_approval"]),
        "material_fields": list(r["material_fields"] or []),
        "org_override": bool(r["org_override"]),
    } for r in rows]


@router.patch("/approval-policy", summary="Set your org's rule for an action (overrides the platform default)")
def set_approval_policy(body: PolicyPatch, session: DbSession,
                        ctx: dict = Depends(require_permission("admin.approval_policy.manage"))):
    import json
    org_id = ctx["org"]["org_id"]
    if body.action_key not in _POLICY_LABELS:
        raise HTTPException(422, {"error": "unknown_action", "message": f"Unknown action: {body.action_key}"})
    mats = body.material_fields if body.material_fields is not None else []
    session.execute(text("""
        INSERT INTO approval_policy (org_id, action_key, requires_approval, material_fields, updated_by, updated_at)
        VALUES (:o, :a, :req, CAST(:m AS jsonb), :u, now())
        ON CONFLICT (org_id, action_key) WHERE org_id IS NOT NULL
        DO UPDATE SET requires_approval = EXCLUDED.requires_approval,
                      material_fields = EXCLUDED.material_fields,
                      updated_by = EXCLUDED.updated_by, updated_at = now()
    """), {"o": org_id, "a": body.action_key, "req": body.requires_approval, "m": json.dumps(mats), "u": ctx["user"]["id"]})
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="approval_policy.update",
                target_type="approval_policy", target_id=body.action_key,
                detail={"requires_approval": body.requires_approval, "material_fields": mats})
    return {"action_key": body.action_key, "requires_approval": body.requires_approval, "material_fields": mats, "org_override": True}


# ── Control center: the customer-admin cockpit (identity + data health + governance) ──────

class OrgPatch(BaseModel):
    legal_name:          Optional[str] = Field(None, max_length=300)
    lei:                 Optional[str] = Field(None, max_length=20)
    eori:                Optional[str] = Field(None, max_length=30)
    filing_contact_email: Optional[str] = Field(None, max_length=255)
    operator_address:    Optional[str] = Field(None, max_length=500)


@router.get("/control-center", summary="Admin cockpit — org identity, data-readiness, governance & access at a glance")
def control_center(session: DbSession, ctx: dict = Depends(require_permission("admin.users.manage"))):
    org_id = ctx["org"]["org_id"]
    org = session.execute(text("""
        SELECT name, legal_name, type, country, lei, eori, filing_contact_email, operator_address
        FROM organizations WHERE org_id = :o
    """), {"o": org_id}).mappings().first()

    sites = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE v.physical_risk_score IS NOT NULL) scored,
               count(*) FILTER (WHERE v.physical_risk_score >= 40) elevated,
               COALESCE(SUM(s.annual_value_eur),0) value_eur
        FROM sc_company_sites s
        LEFT JOIN LATERAL (
            SELECT physical_risk_score FROM v_sc_site_physical_risk v
            WHERE v.site_id = s.site_id AND v.scenario='baseline' AND v.time_horizon='current'
            ORDER BY physical_risk_score DESC NULLS LAST LIMIT 1) v ON true
        WHERE s.org_id = :o
    """), {"o": org_id}).mappings().first()

    plots = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE p.plot_geometry IS NULL AND p.plot_area_ha > 4) needs_polygon,
               count(*) FILTER (WHERE co.eudr_covered) eudr_covered,
               count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination IS NOT NULL) eudr_determined
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o
    """), {"o": org_id}).mappings().first()

    users = session.execute(text("""
        SELECT count(*) n, count(*) FILTER (WHERE status='active') active,
               count(*) FILTER (WHERE last_login_at IS NOT NULL) ever_logged_in
        FROM users WHERE org_id = :o
    """), {"o": org_id}).mappings().first()
    # is there a checker distinct from makers? (someone with approvals.decide)
    n_approvers = session.execute(text("""
        SELECT count(DISTINCT u.user_id) FROM users u
        JOIN user_roles ur ON ur.user_id=u.user_id JOIN role_permissions rp ON rp.role_id=ur.role_id
        JOIN permissions p ON p.permission_id=rp.permission_id
        WHERE u.org_id=:o AND u.status='active' AND p.code='approvals.decide'
    """), {"o": org_id}).scalar()
    pending = session.execute(text("SELECT count(*) FROM approval_requests WHERE org_id=:o AND status='pending'"), {"o": org_id}).scalar()
    audit_30d = session.execute(text("SELECT count(*) FROM access_audit_log WHERE org_id=:o AND created_at > now() - interval '30 days'"), {"o": org_id}).scalar()
    entitlements = session.execute(text("SELECT offering_id FROM org_entitlements WHERE org_id=:o ORDER BY offering_id"), {"o": org_id}).scalars().all()

    # readiness checklist — the "is my house in order" signal (each item pass/fail + a hint)
    identity_ok = bool(org and org["eori"] and org["filing_contact_email"])
    checks = [
        {"key": "identity", "label": "Reporting identity complete (EORI + filing contact)", "ok": identity_ok,
         "hint": "Set EORI and a filing contact email below." if not identity_ok else None},
        {"key": "sites_scored", "label": "All operational sites scored", "ok": (sites["n"] or 0) > 0 and sites["scored"] == sites["n"],
         "hint": f"{(sites['n'] or 0) - (sites['scored'] or 0)} site(s) not yet scored." if (sites["n"] or 0) and sites["scored"] != sites["n"] else ("Add your operational sites." if not sites["n"] else None)},
        {"key": "plots_polygons", "label": "All >4 ha plots have a polygon (EUDR)", "ok": (plots["needs_polygon"] or 0) == 0,
         "hint": f"{plots['needs_polygon']} plot(s) over 4 ha need a boundary polygon." if plots["needs_polygon"] else None},
        {"key": "eudr_run", "label": "EUDR determination run on covered plots", "ok": (plots["eudr_covered"] or 0) == 0 or plots["eudr_determined"] == plots["eudr_covered"],
         "hint": f"{(plots['eudr_covered'] or 0) - (plots['eudr_determined'] or 0)} covered plot(s) not yet checked." if (plots["eudr_covered"] or 0) and plots["eudr_determined"] != plots["eudr_covered"] else None},
        {"key": "second_approver", "label": "A second approver exists (4-eyes works)", "ok": (n_approvers or 0) >= 2,
         "hint": "Only one user can approve — 4-eyes needs a second. Add an approver." if (n_approvers or 0) < 2 else None},
    ]
    passed = sum(1 for c in checks if c["ok"])
    return {
        "organization": {
            "name": org["name"] if org else None, "legal_name": org["legal_name"] if org else None,
            "type": org["type"] if org else None, "country": org["country"] if org else None,
            "lei": org["lei"] if org else None, "eori": org["eori"] if org else None,
            "filing_contact_email": org["filing_contact_email"] if org else None,
            "operator_address": org["operator_address"] if org else None,
        },
        "readiness": {"passed": passed, "total": len(checks), "checks": checks},
        "data": {
            "sites": {"total": sites["n"], "scored": sites["scored"], "elevated": sites["elevated"], "value_eur": float(sites["value_eur"] or 0)},
            "plots": {"total": plots["n"], "eudr_covered": plots["eudr_covered"], "eudr_determined": plots["eudr_determined"], "needs_polygon": plots["needs_polygon"]},
        },
        "governance": {"pending_approvals": pending, "audit_events_30d": audit_30d, "second_approver": (n_approvers or 0) >= 2},
        "access": {"users": users["n"], "active": users["active"], "ever_logged_in": users["ever_logged_in"]},
        "entitlements": list(entitlements),
    }


@router.patch("/organization", summary="Edit the org's reporting identity (audited)")
def patch_organization(body: OrgPatch, session: DbSession,
                       ctx: dict = Depends(require_permission("admin.users.manage"))):
    org_id = ctx["org"]["org_id"]
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise HTTPException(400, {"error": "no_changes", "message": "No fields to update."})
    cols = {"legal_name", "lei", "eori", "filing_contact_email", "operator_address"}
    sets, params = [], {"o": org_id}
    for k, v in changes.items():
        if k in cols:
            sets.append(f"{k} = :{k}"); params[k] = v
    session.execute(text(f"UPDATE organizations SET {', '.join(sets)}, updated_at = now() WHERE org_id = :o"), params)
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="organization.update",
                target_type="organization", target_id=org_id, detail={"changes": changes})
    return {"ok": True, "changes": changes}
