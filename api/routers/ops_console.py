"""Platform-operator console — Tellumen staff, CROSS-TENANT.

The rest of the app is strictly org-scoped and hardened against cross-tenant reads. This router
is the deliberate exception: it reads across every customer org, so it is gated by the
`platform.admin` permission that NO customer role holds (see migration platform_admin_perm and
scripts/seed_platform_operator.py). Read-only — an operator never edits a customer's data here.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/ops", tags=["Platform operator"])


@router.get("/tenants", summary="All customer tenants with health & usage rollups (cross-tenant)")
def tenants(session: DbSession, ctx: dict = Depends(require_permission("platform.admin"))):
    rows = session.execute(text("""
        SELECT o.org_id::text, o.name, o.type, o.country, o.created_at,
               (SELECT count(*) FROM users u WHERE u.org_id=o.org_id) AS users,
               (SELECT count(*) FROM users u WHERE u.org_id=o.org_id AND u.status='active') AS active_users,
               (SELECT count(*) FROM sc_company_sites s WHERE s.org_id=o.org_id) AS sites,
               (SELECT count(*) FROM sc_sourcing_plots p WHERE p.org_id=o.org_id) AS plots,
               (SELECT count(*) FROM approval_requests a WHERE a.org_id=o.org_id AND a.status='pending') AS pending_approvals,
               (SELECT count(*) FROM access_audit_log al WHERE al.org_id=o.org_id AND al.created_at > now() - interval '30 days') AS audit_30d,
               (SELECT max(al.created_at) FROM access_audit_log al WHERE al.org_id=o.org_id) AS last_activity,
               (SELECT COALESCE(array_agg(offering_id ORDER BY offering_id), '{}') FROM org_entitlements e WHERE e.org_id=o.org_id) AS entitlements
        FROM organizations o
        ORDER BY o.name
    """)).mappings().all()
    tenants = [{
        "org_id": r["org_id"], "name": r["name"], "type": r["type"], "country": r["country"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "users": r["users"], "active_users": r["active_users"], "sites": r["sites"], "plots": r["plots"],
        "pending_approvals": r["pending_approvals"], "audit_30d": r["audit_30d"],
        "last_activity": r["last_activity"].isoformat() if r["last_activity"] else None,
        "entitlements": list(r["entitlements"]),
    } for r in rows]
    totals = {
        "tenants": len(tenants),
        "users": sum(t["users"] for t in tenants),
        "sites": sum(t["sites"] for t in tenants),
        "plots": sum(t["plots"] for t in tenants),
        "pending_approvals": sum(t["pending_approvals"] for t in tenants),
    }
    return {"totals": totals, "tenants": tenants}


@router.get("/tenant/{org_id}", summary="One tenant — detail (cross-tenant)")
def tenant(org_id: str, session: DbSession, ctx: dict = Depends(require_permission("platform.admin"))):
    org = session.execute(text("""
        SELECT o.org_id::text, o.name, o.legal_name, o.type, o.country, o.lei, o.eori,
               o.filing_contact_email, o.created_at
        FROM organizations o WHERE o.org_id = :o
    """), {"o": org_id}).mappings().first()
    if not org:
        raise HTTPException(404, {"error": "not_found", "message": "Tenant not found."})
    users = session.execute(text("""
        SELECT u.email, u.full_name, u.status, u.last_login_at,
               COALESCE(array_agg(r.name) FILTER (WHERE r.name IS NOT NULL), '{}') AS roles
        FROM users u LEFT JOIN user_roles ur ON ur.user_id=u.user_id LEFT JOIN roles r ON r.role_id=ur.role_id
        WHERE u.org_id = :o GROUP BY u.user_id, u.email, u.full_name, u.status, u.last_login_at ORDER BY u.email
    """), {"o": org_id}).mappings().all()
    ents = session.execute(text("SELECT offering_id FROM org_entitlements WHERE org_id=:o ORDER BY offering_id"), {"o": org_id}).scalars().all()
    recent = session.execute(text("""
        SELECT al.action, al.created_at, u.email FROM access_audit_log al
        LEFT JOIN users u ON u.user_id=al.actor_user_id
        WHERE al.org_id=:o ORDER BY al.created_at DESC LIMIT 15
    """), {"o": org_id}).mappings().all()
    return {
        "organization": {**{k: org[k] for k in ("org_id", "name", "legal_name", "type", "country", "lei", "eori", "filing_contact_email")},
                         "created_at": org["created_at"].isoformat() if org["created_at"] else None},
        "users": [{"email": u["email"], "full_name": u["full_name"], "status": u["status"],
                   "last_login_at": u["last_login_at"].isoformat() if u["last_login_at"] else None,
                   "roles": list(u["roles"])} for u in users],
        "entitlements": list(ents),
        "recent_activity": [{"action": r["action"], "email": r["email"],
                             "created_at": r["created_at"].isoformat() if r["created_at"] else None} for r in recent],
    }
