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


class ApprovalAssign(BaseModel):
    # null clears the assignment (back to "any approver can pick it up")
    assignee_user_id: Optional[str] = None


def _serialize(r) -> dict:
    return {
        "id": str(r["request_id"]), "request_type": r["request_type"],
        "title": r["title"], "payload": r["payload"], "status": r["status"],
        "maker_email": r["maker_email"], "checker_email": r["checker_email"],
        "assignee_email": r.get("assignee_email"),
        "assignee_user_id": str(r["assigned_to_user_id"]) if r.get("assigned_to_user_id") else None,
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
               ar.created_at, ar.decided_at, ar.maker_user_id, ar.assigned_to_user_id,
               mu.email AS maker_email, cu.email AS checker_email, au.email AS assignee_email
        FROM   approval_requests ar
        LEFT   JOIN users mu ON mu.user_id = ar.maker_user_id
        LEFT   JOIN users cu ON cu.user_id = ar.checker_user_id
        LEFT   JOIN users au ON au.user_id = ar.assigned_to_user_id
        WHERE  ar.org_id = :o
          AND  (CAST(:st AS text) IS NULL OR ar.status = :st)
        ORDER  BY ar.created_at DESC
    """), {"o": ctx["org"]["org_id"], "st": status}).mappings().all()
    # flag which ones the caller may NOT decide (their own) + whether it's assigned to them, so the UI can shape
    me = ctx["user"]["id"]
    return [{**_serialize(r), "is_own": str(r["maker_user_id"]) == me,
             "assigned_to_me": str(r["assigned_to_user_id"]) == me if r["assigned_to_user_id"] else False}
            for r in rows]


@router.get("/deciders", summary="Users who can decide approvals (candidate assignees)")
def deciders(session: DbSession, ctx: dict = Depends(require_permission("approvals.view"))):
    """The org's approvers — users whose roles carry approvals.decide. Used to populate the
    'assign to…' picker so a request can be routed to a named second pair of eyes."""
    rows = session.execute(text("""
        SELECT DISTINCT u.user_id, u.email, u.full_name
        FROM   users u
        JOIN   user_roles ur ON ur.user_id = u.user_id
        JOIN   role_permissions rp ON rp.role_id = ur.role_id
        JOIN   permissions p ON p.permission_id = rp.permission_id
        WHERE  u.org_id = :o AND p.code = 'approvals.decide' AND u.status = 'active'
        ORDER  BY u.email
    """), {"o": ctx["org"]["org_id"]}).mappings().all()
    return [{"user_id": str(r["user_id"]), "email": r["email"], "name": r["full_name"]} for r in rows]


@router.post("/{request_id}/assign", summary="Assign a pending request to a specific approver (routing)")
def assign(request_id: str, body: ApprovalAssign, session: DbSession,
           ctx: dict = Depends(require_permission("approvals.view"))):
    org_id = ctx["org"]["org_id"]
    row = session.execute(text("""
        SELECT maker_user_id, status FROM approval_requests WHERE request_id = :r AND org_id = :o
    """), {"r": request_id, "o": org_id}).mappings().first()
    if not row:
        raise HTTPException(404, {"error": "not_found", "message": "Approval request not found."})
    if row["status"] != "pending":
        raise HTTPException(409, {"error": "already_decided", "message": f"Request is already {row['status']}."})
    # only the maker or a decider may route the request (assignment ≠ deciding, but it shouldn't be open to all)
    if str(row["maker_user_id"]) != ctx["user"]["id"] and "approvals.decide" not in ctx["permissions"]:
        raise HTTPException(403, {"error": "forbidden",
                                  "message": "Only the requester or an approver can assign this request."})
    assignee = body.assignee_user_id
    if assignee and str(row["maker_user_id"]) == assignee:
        raise HTTPException(422, {"error": "maker_cannot_be_assignee",
                                  "message": "The maker can't approve their own request (4-eyes) — assign it to a different approver."})
    if assignee:
        ok = session.execute(text("""
            SELECT 1 FROM users u JOIN user_roles ur ON ur.user_id = u.user_id
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.permission_id = rp.permission_id
            WHERE u.user_id = CAST(:a AS uuid) AND u.org_id = :o AND p.code = 'approvals.decide'
        """), {"a": assignee, "o": org_id}).first()
        if not ok:
            raise HTTPException(422, {"error": "invalid_assignee",
                                      "message": "The assignee must be an approver in this organisation."})
    session.execute(text("UPDATE approval_requests SET assigned_to_user_id = CAST(:a AS uuid) WHERE request_id = :r"),
                    {"a": assignee, "r": request_id})
    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="approval.assign",
                target_type="approval", target_id=request_id, detail={"assignee_user_id": assignee})
    return {"id": request_id, "assignee_user_id": assignee}


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
    # Filing approval: a filing.approve request clearing (or being sent back) drives the filing lifecycle.
    # 4-eyes is already enforced above (checker ≠ maker), so an approved filing is one a second pair of eyes signed.
    elif row["request_type"] == "filing.approve":
        from services.governance.filings import mark_approved, mark_returned, FilingError
        fid = (row["payload"] or {}).get("filing_id")
        try:
            if body.decision == "approved":
                applied = mark_approved(session, org_id, fid, ctx["user"]["id"], reason=body.reason)
            elif body.decision == "returned":
                applied = mark_returned(session, org_id, fid, ctx["user"]["id"], reason=body.reason)
            else:  # rejected
                applied = mark_returned(session, org_id, fid, ctx["user"]["id"], reason=body.reason, rejected=True)
        except FilingError as e:
            raise HTTPException(409, {"error": "apply_failed",
                                      "message": f"Decision recorded, but could not update the filing: {e}"})
    # Cell-level manual override on the final form: on approval it takes effect over the frozen snapshot;
    # 4-eyes (checker ≠ maker) is enforced above, so an approved override carries a second person's sign-off.
    elif row["request_type"] == "filing.cell_override":
        from services.governance.filing_overrides import apply_decision
        applied = apply_decision(session, org_id, row["payload"] or {}, body.decision, ctx["user"]["id"])

    write_audit(session, org_id=org_id, actor_user_id=ctx["user"]["id"], action="approval.decide",
                target_type="approval", target_id=request_id,
                detail={"decision": body.decision, "reason": body.reason, "request_type": row["request_type"]})

    # Forward the governed decision to any subscribed customer system (best-effort; never blocks the
    # decision or fails it if a webhook is down — delivery runs in a background thread and is logged).
    try:
        from services.integrations.webhooks import emit_event
        emit_event(session, org_id, "approval.decided", {
            "request_id": request_id, "request_type": row["request_type"],
            "decision": body.decision, "checker": ctx["user"].get("email"),
        })
    except Exception:
        pass

    return {"id": request_id, "status": body.decision, "applied": applied}
