"""
Service portal — customer support & requests hub.

Customers raise requests (data, reports, onboarding, bugs, questions), converse with Tellumen support on a
threaded message log, and track status through to resolution. Org-scoped; requires the portal.use
permission. The "our side" of the same conversation (a Tellumen operator replying, cross-tenant) lives in
api/routers/ops_console.py under /v1/ops/support.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/portal", tags=["Service Portal"])

CATEGORIES = ["data", "report", "onboarding", "bug", "question", "other"]


class RequestCreate(BaseModel):
    category: str = Field(..., max_length=40)
    subject:  str = Field(..., min_length=3, max_length=200)
    body:     Optional[str] = Field(None, max_length=4000)
    priority: str = Field("normal", pattern="^(low|normal|high|urgent)$")


class RequestPatch(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|resolved)$")


class MessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=4000)


def _serialize(r) -> dict:
    # awaiting_customer = Tellumen replied last and it isn't resolved → the ball is in the customer's court.
    last_side = r.get("last_side")
    return {
        "id": str(r["request_id"]), "category": r["category"], "subject": r["subject"],
        "body": r["body"], "priority": r["priority"], "status": r["status"],
        "requester_email": r.get("requester_email"),
        "message_count": int(r.get("message_count") or 0),
        "awaiting_customer": (last_side == "support" and r["status"] != "resolved"),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        "first_response_at": r["first_response_at"].isoformat() if r.get("first_response_at") else None,
        "resolved_at": r["resolved_at"].isoformat() if r.get("resolved_at") else None,
        "last_activity": (r["last_activity"].isoformat() if r.get("last_activity") else
                          (r["updated_at"].isoformat() if r["updated_at"] else None)),
    }


def _msg(m) -> dict:
    return {
        "id": str(m["message_id"]), "author_side": m["author_side"],
        "author_email": m.get("author_email"), "author_name": m.get("author_name"),
        "body": m["body"], "created_at": m["created_at"].isoformat() if m["created_at"] else None,
    }


# The list SELECT — one row per request with rollups (message count, who spoke last, last activity).
_LIST_COLS = """
    sr.request_id, sr.category, sr.subject, sr.body, sr.priority, sr.status,
    sr.created_at, sr.updated_at, sr.first_response_at, sr.resolved_at,
    u.email AS requester_email,
    (SELECT count(*)          FROM service_request_messages m WHERE m.request_id = sr.request_id) AS message_count,
    (SELECT m.author_side     FROM service_request_messages m WHERE m.request_id = sr.request_id ORDER BY m.created_at DESC LIMIT 1) AS last_side,
    GREATEST(sr.updated_at, COALESCE(
        (SELECT max(m.created_at) FROM service_request_messages m WHERE m.request_id = sr.request_id), sr.updated_at)) AS last_activity
"""


@router.post("/requests", status_code=201, summary="Raise a service request")
def create_request(body: RequestCreate, session: DbSession,
                   ctx: dict = Depends(require_permission("portal.use"))):
    if body.category not in CATEGORIES:
        raise HTTPException(422, {"error": "bad_category",
                                  "message": f"category must be one of {CATEGORIES}"})
    rid = session.execute(text("""
        INSERT INTO service_requests (org_id, requester_user_id, category, subject, body, priority)
        VALUES (:o, :u, :c, :s, :b, :p)
        RETURNING request_id
    """), {"o": ctx["org"]["org_id"], "u": ctx["user"]["id"], "c": body.category,
           "s": body.subject, "b": body.body, "p": body.priority}).scalar()
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="support.request.create", target_type="service_request", target_id=str(rid),
                detail={"category": body.category, "subject": body.subject, "priority": body.priority})
    return {"id": str(rid), "status": "open"}


@router.get("/requests", summary="List your organization's service requests")
def list_requests(session: DbSession, ctx: dict = Depends(require_permission("portal.use"))):
    rows = session.execute(text(f"""
        SELECT {_LIST_COLS}
        FROM   service_requests sr
        LEFT   JOIN users u ON u.user_id = sr.requester_user_id
        WHERE  sr.org_id = :o
        ORDER  BY last_activity DESC
    """), {"o": ctx["org"]["org_id"]}).mappings().all()
    return [_serialize(r) for r in rows]


@router.get("/requests/{request_id}", summary="One request with its full conversation thread")
def get_request(request_id: str, session: DbSession,
                ctx: dict = Depends(require_permission("portal.use"))):
    r = session.execute(text(f"""
        SELECT {_LIST_COLS}
        FROM   service_requests sr
        LEFT   JOIN users u ON u.user_id = sr.requester_user_id
        WHERE  sr.request_id = :r AND sr.org_id = :o
    """), {"r": request_id, "o": ctx["org"]["org_id"]}).mappings().first()
    if not r:
        raise HTTPException(404, {"error": "not_found", "message": "Request not found."})
    msgs = session.execute(text("""
        SELECT m.message_id, m.author_side, m.body, m.created_at,
               u.email AS author_email, u.full_name AS author_name
        FROM   service_request_messages m
        LEFT   JOIN users u ON u.user_id = m.author_user_id
        WHERE  m.request_id = :r
        ORDER  BY m.created_at ASC
    """), {"r": request_id}).mappings().all()
    return {"request": _serialize(r), "messages": [_msg(m) for m in msgs]}


@router.post("/requests/{request_id}/messages", status_code=201, summary="Add a reply to your request")
def add_message(request_id: str, body: MessageCreate, session: DbSession,
                ctx: dict = Depends(require_permission("portal.use"))):
    cur = session.execute(text(
        "SELECT status FROM service_requests WHERE request_id = :r AND org_id = :o"),
        {"r": request_id, "o": ctx["org"]["org_id"]}).mappings().first()
    if not cur:
        raise HTTPException(404, {"error": "not_found", "message": "Request not found."})
    mid = session.execute(text("""
        INSERT INTO service_request_messages (request_id, author_user_id, author_side, body)
        VALUES (:r, :u, 'customer', :b) RETURNING message_id
    """), {"r": request_id, "u": ctx["user"]["id"], "b": body.body}).scalar()
    # A customer replying to a resolved request reopens it — the conversation isn't done on their side.
    reopened = cur["status"] == "resolved"
    session.execute(text(f"""
        UPDATE service_requests
        SET updated_at = now(){", status = 'open', resolved_at = NULL" if reopened else ""}
        WHERE request_id = :r
    """), {"r": request_id})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="support.request.reply", target_type="service_request", target_id=request_id,
                detail={"reopened": reopened})
    return {"id": str(mid), "reopened": reopened}


@router.patch("/requests/{request_id}", summary="Update a request's status")
def patch_request(request_id: str, body: RequestPatch, session: DbSession,
                  ctx: dict = Depends(require_permission("portal.use"))):
    updated = session.execute(text("""
        UPDATE service_requests
        SET status = :s, updated_at = now(),
            resolved_at = CASE WHEN :res THEN now() ELSE NULL END
        WHERE  request_id = :r AND org_id = :o
        RETURNING request_id
    """), {"s": body.status, "res": body.status == "resolved",
           "r": request_id, "o": ctx["org"]["org_id"]}).scalar()
    if not updated:
        raise HTTPException(404, {"error": "not_found", "message": "Request not found."})
    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="support.request.status", target_type="service_request", target_id=request_id,
                detail={"status": body.status})
    return {"id": request_id, "status": body.status}
