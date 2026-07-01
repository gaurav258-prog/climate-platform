"""
Service portal — customer support & requests hub.

Customers raise requests (data, reports, onboarding, bugs, questions) and track
their status. Org-scoped; requires the portal.use permission.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission

router = APIRouter(prefix="/v1/portal", tags=["Service Portal"])

CATEGORIES = ["data", "report", "onboarding", "bug", "question", "other"]


class RequestCreate(BaseModel):
    category: str = Field(..., max_length=40)
    subject:  str = Field(..., min_length=3, max_length=200)
    body:     Optional[str] = Field(None, max_length=4000)
    priority: str = Field("normal", pattern="^(low|normal|high|urgent)$")


class RequestPatch(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|resolved)$")


def _serialize(r) -> dict:
    return {
        "id": str(r["request_id"]), "category": r["category"], "subject": r["subject"],
        "body": r["body"], "priority": r["priority"], "status": r["status"],
        "requester_email": r.get("requester_email"),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


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
    return {"id": str(rid), "status": "open"}


@router.get("/requests", summary="List your organization's service requests")
def list_requests(session: DbSession, ctx: dict = Depends(require_permission("portal.use"))):
    rows = session.execute(text("""
        SELECT sr.request_id, sr.category, sr.subject, sr.body, sr.priority, sr.status,
               sr.created_at, sr.updated_at, u.email AS requester_email
        FROM   service_requests sr
        LEFT   JOIN users u ON u.user_id = sr.requester_user_id
        WHERE  sr.org_id = :o
        ORDER  BY sr.created_at DESC
    """), {"o": ctx["org"]["org_id"]}).mappings().all()
    return [_serialize(r) for r in rows]


@router.patch("/requests/{request_id}", summary="Update a request's status")
def patch_request(request_id: str, body: RequestPatch, session: DbSession,
                  ctx: dict = Depends(require_permission("portal.use"))):
    updated = session.execute(text("""
        UPDATE service_requests SET status = :s, updated_at = now()
        WHERE  request_id = :r AND org_id = :o
        RETURNING request_id
    """), {"s": body.status, "r": request_id, "o": ctx["org"]["org_id"]}).scalar()
    if not updated:
        raise HTTPException(404, {"error": "not_found", "message": "Request not found."})
    return {"id": request_id, "status": body.status}
