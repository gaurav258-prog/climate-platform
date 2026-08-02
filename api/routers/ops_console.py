"""Platform-operator console — Tellumen staff, CROSS-TENANT.

The rest of the app is strictly org-scoped and hardened against cross-tenant reads. This router
is the deliberate exception: it reads across every customer org, so it is gated by the
`platform.admin` permission that NO customer role holds (see migration platform_admin_perm and
scripts/seed_platform_operator.py). Read-only — an operator never edits a customer's data here.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.security import create_access_token
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/ops", tags=["Platform operator"])


class ImpersonateBody(BaseModel):
    org_id: str = Field(..., min_length=1)


@router.post("/impersonate", summary="Open a customer tenant's workspace (view-as, audited)")
def impersonate(body: ImpersonateBody, session: DbSession,
                ctx: dict = Depends(require_permission("platform.admin"))):
    """Mint a session token as an admin of the target tenant, so a platform operator can enter that
    customer's full workspace + cockpit from one login. Read/act happens as that tenant; the ENTRY is
    recorded in the tenant's own audit log (transparency) against the real operator."""
    org = session.execute(text("SELECT name, type FROM organizations WHERE org_id=:o"), {"o": body.org_id}).mappings().first()
    if not org:
        raise HTTPException(404, {"error": "not_found", "message": "Tenant not found."})
    if org["type"] == "platform":
        raise HTTPException(422, {"error": "not_a_tenant", "message": "Cannot view-as the platform org itself."})
    # prefer an active admin of the tenant; else any active user
    target = session.execute(text("""
        SELECT u.user_id::text, u.email, u.full_name,
               bool_or(r.name = 'admin') AS is_admin
        FROM users u LEFT JOIN user_roles ur ON ur.user_id=u.user_id LEFT JOIN roles r ON r.role_id=ur.role_id
        WHERE u.org_id=:o AND u.status='active'
        GROUP BY u.user_id, u.email, u.full_name
        ORDER BY is_admin DESC, u.created_at ASC LIMIT 1
    """), {"o": body.org_id}).mappings().first()
    if not target:
        raise HTTPException(409, {"error": "no_user", "message": "This tenant has no active user to view as."})

    operator_email = ctx["user"]["email"]
    token = create_access_token(user_id=target["user_id"], org_id=body.org_id,
                                extra={"impersonated_by": operator_email})
    write_audit(session, org_id=body.org_id, actor_user_id=ctx["user"]["id"], action="impersonation.start",
                target_type="organization", target_id=body.org_id,
                detail={"operator": operator_email, "as_user": target["email"]})
    return {"token": token, "tenant_name": org["name"], "as_user_email": target["email"], "as_user_name": target["full_name"]}


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


# ─────────────────────────── Support queue (the "with us" side) ───────────────────────────
# The customer raises requests in their own tenant (/v1/portal). Here a Tellumen operator sees them ACROSS
# every tenant, replies on the shared thread, and drives them to resolution. An operator's reply is written
# into the customer's OWN audit log (transparency), exactly like impersonation entries.

class SupportReply(BaseModel):
    body:   str = Field(..., min_length=1, max_length=4000)
    status: Optional[str] = Field(None, pattern="^(open|in_progress|resolved)$")


def _sr_serialize(r) -> dict:
    last_side = r.get("last_side")
    return {
        "id": str(r["request_id"]), "org_id": str(r["org_id"]), "org_name": r.get("org_name"),
        "category": r["category"], "subject": r["subject"], "body": r["body"],
        "priority": r["priority"], "status": r["status"], "requester_email": r.get("requester_email"),
        "message_count": int(r.get("message_count") or 0),
        "awaiting_support": (last_side is None or last_side == "customer") and r["status"] != "resolved",
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "first_response_at": r["first_response_at"].isoformat() if r.get("first_response_at") else None,
        "resolved_at": r["resolved_at"].isoformat() if r.get("resolved_at") else None,
        "last_activity": r["last_activity"].isoformat() if r.get("last_activity") else None,
    }


_SR_COLS = """
    sr.request_id, sr.org_id, o.name AS org_name, sr.category, sr.subject, sr.body, sr.priority, sr.status,
    sr.created_at, sr.first_response_at, sr.resolved_at, u.email AS requester_email,
    (SELECT count(*)      FROM service_request_messages m WHERE m.request_id = sr.request_id) AS message_count,
    (SELECT m.author_side FROM service_request_messages m WHERE m.request_id = sr.request_id ORDER BY m.created_at DESC LIMIT 1) AS last_side,
    GREATEST(sr.updated_at, COALESCE(
        (SELECT max(m.created_at) FROM service_request_messages m WHERE m.request_id = sr.request_id), sr.updated_at)) AS last_activity
"""


@router.get("/support", summary="Support queue — every tenant's service requests (cross-tenant)")
def support_queue(session: DbSession, ctx: dict = Depends(require_permission("platform.admin")),
                  status: str = Query("open", pattern="^(open|in_progress|resolved|all)$")):
    where = "" if status == "all" else "WHERE sr.status = :st"
    rows = session.execute(text(f"""
        SELECT {_SR_COLS}
        FROM   service_requests sr
        JOIN   organizations o ON o.org_id = sr.org_id
        LEFT   JOIN users u ON u.user_id = sr.requester_user_id
        {where}
        ORDER  BY (sr.status = 'resolved'), sr.priority = 'urgent' DESC, last_activity DESC
    """), ({} if status == "all" else {"st": status})).mappings().all()
    items = [_sr_serialize(r) for r in rows]
    open_n = sum(1 for i in items if i["status"] != "resolved")
    awaiting = sum(1 for i in items if i["awaiting_support"])
    return {"totals": {"shown": len(items), "open": open_n, "awaiting_support": awaiting}, "requests": items}


@router.get("/support/{request_id}", summary="One request + its thread (cross-tenant)")
def support_detail(request_id: str, session: DbSession,
                   ctx: dict = Depends(require_permission("platform.admin"))):
    r = session.execute(text(f"""
        SELECT {_SR_COLS}
        FROM   service_requests sr
        JOIN   organizations o ON o.org_id = sr.org_id
        LEFT   JOIN users u ON u.user_id = sr.requester_user_id
        WHERE  sr.request_id = :r
    """), {"r": request_id}).mappings().first()
    if not r:
        raise HTTPException(404, {"error": "not_found", "message": "Request not found."})
    msgs = session.execute(text("""
        SELECT m.message_id, m.author_side, m.body, m.created_at,
               u.email AS author_email, u.full_name AS author_name
        FROM   service_request_messages m
        LEFT   JOIN users u ON u.user_id = m.author_user_id
        WHERE  m.request_id = :r ORDER BY m.created_at ASC
    """), {"r": request_id}).mappings().all()
    return {"request": _sr_serialize(r), "messages": [
        {"id": str(m["message_id"]), "author_side": m["author_side"], "author_email": m.get("author_email"),
         "author_name": m.get("author_name"), "body": m["body"],
         "created_at": m["created_at"].isoformat() if m["created_at"] else None} for m in msgs]}


@router.post("/support/{request_id}/reply", status_code=201, summary="Reply as Tellumen support (cross-tenant)")
def support_reply(request_id: str, body: SupportReply, session: DbSession,
                  ctx: dict = Depends(require_permission("platform.admin"))):
    req = session.execute(text(
        "SELECT org_id, status FROM service_requests WHERE request_id = :r"),
        {"r": request_id}).mappings().first()
    if not req:
        raise HTTPException(404, {"error": "not_found", "message": "Request not found."})
    mid = session.execute(text("""
        INSERT INTO service_request_messages (request_id, author_user_id, author_side, body)
        VALUES (:r, :u, 'support', :b) RETURNING message_id
    """), {"r": request_id, "u": ctx["user"]["id"], "b": body.body}).scalar()
    # Status: an explicit choice wins; otherwise a first reply on an 'open' request moves it to in_progress.
    new_status = body.status or ("in_progress" if req["status"] == "open" else req["status"])
    session.execute(text("""
        UPDATE service_requests
        SET status = :s, updated_at = now(),
            first_response_at = COALESCE(first_response_at, now()),
            resolved_at = CASE WHEN :res THEN now() ELSE NULL END
        WHERE request_id = :r
    """), {"s": new_status, "res": new_status == "resolved", "r": request_id})
    # Recorded in the CUSTOMER's audit log — the tenant can see that Tellumen support replied.
    write_audit(session, org_id=req["org_id"], actor_user_id=ctx["user"]["id"],
                action="support.reply", target_type="service_request", target_id=request_id,
                detail={"operator": ctx["user"]["email"], "status": new_status})
    return {"id": str(mid), "status": new_status}
