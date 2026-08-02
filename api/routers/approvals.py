"""
Approval requests — the generic 4-eyes (maker-checker) workflow.

Mirrors ml/regulatory/packager.py: the checker must differ from the maker. This
is enforced both here (422) and by a DB CHECK constraint on approval_requests.
A maker submits a request (e.g. report.publish); a different user with
approvals.decide clears it.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit

router = APIRouter(prefix="/v1/approvals", tags=["Approvals"])


class ApprovalCreate(BaseModel):
    request_type: str = Field(..., min_length=1, max_length=60)
    title:        Optional[str] = Field(None, max_length=300)
    payload:      dict = Field(default_factory=dict)


class ApprovalDecision(BaseModel):
    # 'returned' = send back to the maker for more info (not terminal; the change is NOT applied)
    decision: str = Field(..., pattern="^(approved|rejected|returned)$")
    reason:   Optional[str] = None


def _serialize(r) -> dict:
    return {
        "id": str(r["request_id"]), "request_type": r["request_type"],
        "title": r["title"], "payload": r["payload"], "status": r["status"],
        "maker_email": r["maker_email"], "checker_email": r["checker_email"],
        "reason": r["reason"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
    }


@router.post("", status_code=201, summary="Submit a request for approval (maker)")
def create_approval(body: ApprovalCreate, session: DbSession,
                    ctx: dict = Depends(require_permission("approvals.create"))):
    import json
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o, :t, :ti, CAST(:p AS jsonb), :m)
        RETURNING request_id
    """), {"o": ctx["org"]["org_id"], "t": body.request_type, "ti": body.title,
           "p": json.dumps(body.payload), "m": ctx["user"]["id"]}).scalar()

    write_audit(session, org_id=ctx["org"]["org_id"], actor_user_id=ctx["user"]["id"],
                action="approval.create", target_type="approval", target_id=str(rid),
                detail={"request_type": body.request_type, "title": body.title})
    return {"id": str(rid), "status": "pending"}


@router.get("", summary="List approval requests")
def list_approvals(session: DbSession, status: Optional[str] = Query(None),
                   ctx: dict = Depends(require_permission("approvals.view"))):
    rows = session.execute(text("""
        SELECT ar.request_id, ar.request_type, ar.title, ar.payload, ar.status, ar.reason,
               ar.created_at, ar.decided_at, ar.maker_user_id,
               mu.email AS maker_email, cu.email AS checker_email
        FROM   approval_requests ar
        LEFT   JOIN users mu ON mu.user_id = ar.maker_user_id
        LEFT   JOIN users cu ON cu.user_id = ar.checker_user_id
        WHERE  ar.org_id = :o
          AND  (CAST(:st AS text) IS NULL OR ar.status = :st)
        ORDER  BY ar.created_at DESC
    """), {"o": ctx["org"]["org_id"], "st": status}).mappings().all()
    # flag which ones the caller may NOT decide (their own) so the UI can disable
    me = ctx["user"]["id"]
    return [{**_serialize(r), "is_own": str(r["maker_user_id"]) == me} for r in rows]


@router.post("/{request_id}/decide", summary="Approve or reject (checker — must differ from maker)")
def decide(request_id: str, body: ApprovalDecision, session: DbSession,
           ctx: dict = Depends(require_permission("approvals.decide"))):
    org_id = ctx["org"]["org_id"]
    row = session.execute(text("""
        SELECT maker_user_id, status, request_type, payload FROM approval_requests
        WHERE  request_id = :r AND org_id = :o
    """), {"r": request_id, "o": org_id}).mappings().first()
    if not row:
        raise HTTPException(404, {"error": "not_found", "message": "Approval request not found."})
    if row["status"] != "pending":
        raise HTTPException(409, {"error": "already_decided",
                                  "message": f"Request is already {row['status']}."})
    if str(row["maker_user_id"]) == ctx["user"]["id"]:
        raise HTTPException(422, {"error": "maker_checker_violation",
                                  "message": "The maker cannot approve their own request (4-eyes)."})
    if row["request_type"] == "submission.release" and "submissions.release" not in ctx["permissions"]:
        raise HTTPException(403, {"error": "forbidden",
                                  "message": "Missing permission: submissions.release"})

    session.execute(text("""
        UPDATE approval_requests
        SET    status = :s, checker_user_id = :c, reason = :reason, decided_at = now()
        WHERE  request_id = :r
    """), {"s": body.decision, "c": ctx["user"]["id"], "reason": body.reason, "r": request_id})

    if row["request_type"] == "submission.release" and body.decision in ("approved", "rejected"):
        new_status = "released" if body.decision == "approved" else "rejected"
        try:
            session.execute(text(f"""
                UPDATE bank_disclosure_submissions
                SET    status = :s, checker_user_id = :c, checker_at = now(),
                       released_at = {"now()" if new_status == "released" else "NULL"}
                WHERE  approval_request_id = :r
            """), {"s": new_status, "c": ctx["user"]["id"], "r": request_id})
        except Exception as e:
            raise HTTPException(409, {"error": "submission_transition_failed",
                                      "message": f"Could not {new_status} the linked submission: {e}"})

    # Governed location changes: apply the mutation on approval (shares the exact same apply path
    # the direct edit uses, so an approved change is identical to a direct one). Audited within.
    applied = None
    if body.decision == "approved" and row["request_type"].startswith("supply."):
        from services.governance.location_governance import apply_location_change
        try:
            applied = apply_location_change(session, row["request_type"], row["payload"],
                                            actor_user_id=ctx["user"]["id"], org_id=org_id)
        except Exception as e:
            raise HTTPException(409, {"error": "apply_failed",
                                      "message": f"Approved, but could not apply the change: {e}"})
    elif body.decision == "approved" and row["request_type"].startswith("config."):
        from services.governance.config_governance import apply_config_change
        try:
            applied = apply_config_change(session, row["request_type"], row["payload"],
                                          actor_user_id=ctx["user"]["id"], org_id=org_id)
        except Exception as e:
            raise HTTPException(409, {"error": "apply_failed",
                                      "message": f"Approved, but could not apply the change: {e}"})

    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="approval.decide",
                target_type="approval", target_id=request_id,
                detail={"decision": body.decision, "reason": body.reason, "request_type": row["request_type"]})
    return {"id": request_id, "status": body.decision, "applied": applied}
