"""
Approval requests — the generic 4-eyes (maker-checker) workflow.

Mirrors ml/regulatory/packager.py: the checker must differ from the maker. This
is enforced both here (422) and by a DB CHECK constraint on approval_requests.
A maker submits a request (e.g. report.publish); a different user with
approvals.decide clears it. A pending request whose approval policy is switched off is withdrawn by the
platform (services/governance/approval_policy_sweep.py) — flagged, audited, never applied.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.deps import DbSession, require_permission
from api.services.rbac import write_audit
from core import messages
from core.errors import UserError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/approvals", tags=["Approvals"])


class ApprovalCreate(BaseModel):
    request_type: str = Field(..., min_length=1, max_length=60)
    title:        Optional[str] = Field(None, max_length=300)
    payload:      dict = Field(default_factory=dict)


# a request type whose mechanism is retired: no new request, and a pending one can only be rejected (closed). The
# separate bank disclosure submission (E99) froze the whole disclosure outside the filing lifecycle; a disclosure is
# filed through the filing (freeze, four eyes, submit, amend) and compared period over period by its variance.
RETIRED_TYPES = {"submission.release"}


def _not_applied(e: Exception) -> UserError:
    """A decision whose change could not be applied. The session rolls back on the error, so the decision is NOT
    recorded and the request stays pending — the words must say so (they claimed the decision was recorded). A refusal
    already in customer words passes its label on; any other cause goes to the log."""
    code = getattr(e, "code", None)          # a UserError, or an error that carries a catalogue code (a release)
    if isinstance(code, str) and code in messages.catalogue():
        return UserError("admin.approvals.not_applied", reason=messages.render(code, **(getattr(e, "params", None) or {}))["label"])
    logger.warning("approval not applied: %s", e)
    return UserError("admin.approvals.not_applied", reason=messages.label("admin.approvals.apply_failed"))


class ApprovalDecision(BaseModel):
    # 'returned' = send back to the maker for more info (not terminal; the change is NOT applied)
    decision: str = Field(..., pattern="^(approved|rejected|returned)$")
    reason:   Optional[str] = None


class ApprovalAssign(BaseModel):
    # null clears the assignment (back to "any approver can pick it up")
    assignee_user_id: Optional[str] = None


def _title(stored):
    from services.governance.approval_view import title
    return title(stored)


def _details(request_type: str, payload: dict) -> list[dict]:
    from services.governance.approval_view import details
    return details(request_type, payload)


def _serialize(r) -> dict:
    return {
        "id": str(r["request_id"]), "request_type": r["request_type"],
        "title": r["title"], "title_label": _title(r["title"]), "payload": r["payload"], "status": r["status"],
        "maker_email": r["maker_email"], "checker_email": r["checker_email"],
        "assignee_email": r.get("assignee_email"),
        "assignee_user_id": str(r["assigned_to_user_id"]) if r.get("assigned_to_user_id") else None,
        "reason": r["reason"], "status_label": messages.name("admin.approval_status", r["status"]),
        "details": _details(r["request_type"], r["payload"] or {}),
        # 'withdrawn' = closed by the platform, not a checker: the org's policy stopped governing the action while the
        # request was pending. Never applied. policy_off is the UI flag; withdrawn_cause the machine cause.
        "withdrawn_cause": r.get("withdrawn_cause"),
        "policy_off": r.get("withdrawn_cause") == "policy_no_longer_requires_approval",
        "policy_off_message": (messages.render("admin.approvals.policy_off")
                               if r.get("withdrawn_cause") == "policy_no_longer_requires_approval" else None),
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "decided_at": r["decided_at"].isoformat() if r["decided_at"] else None,
    }


@router.post("", status_code=201, summary="Submit a request for approval (maker)")
def create_approval(body: ApprovalCreate, session: DbSession,
                    ctx: dict = Depends(require_permission("approvals.create"))):
    import json
    if body.request_type in RETIRED_TYPES:
        raise UserError("admin.approvals.retired")
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
        SELECT ar.request_id, ar.request_type, ar.title, ar.payload, ar.status, ar.reason, ar.withdrawn_cause,
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
        raise UserError("admin.approvals.not_found")
    if row["status"] != "pending":
        raise UserError("admin.approvals.already_decided", status=messages.name("admin.approval_status", row["status"]))
    # only the maker or a decider may route the request (assignment ≠ deciding, but it shouldn't be open to all)
    if str(row["maker_user_id"]) != ctx["user"]["id"] and "approvals.decide" not in ctx["permissions"]:
        raise UserError("admin.approvals.assign_forbidden")
    assignee = body.assignee_user_id
    if assignee and str(row["maker_user_id"]) == assignee:
        raise UserError("admin.approvals.maker_assignee")
    if assignee:
        ok = session.execute(text("""
            SELECT 1 FROM users u JOIN user_roles ur ON ur.user_id = u.user_id
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.permission_id = rp.permission_id
            WHERE u.user_id = CAST(:a AS uuid) AND u.org_id = :o AND p.code = 'approvals.decide'
        """), {"a": assignee, "o": org_id}).first()
        if not ok:
            raise UserError("admin.approvals.not_an_approver")
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
        raise UserError("admin.approvals.not_found")
    if row["status"] != "pending":
        raise UserError("admin.approvals.already_decided", status=messages.name("admin.approval_status", row["status"]))
    if str(row["maker_user_id"]) == ctx["user"]["id"]:
        raise UserError("admin.approvals.own_request")
    if row["request_type"] in RETIRED_TYPES and body.decision == "approved":
        raise UserError("admin.approvals.retired_decide")
    for rtype, perm in (("reference.release_land", "reference.release_review"), ("calibration.publish", "calibration.review"),
                        ("submission.release", "submissions.release")):
        if row["request_type"] == rtype and perm not in ctx["permissions"]:
            raise UserError("admin.approvals.needs_permission", permission=messages.name("admin.permission", perm))

    session.execute(text("""
        UPDATE approval_requests
        SET    status = :s, checker_user_id = :c, reason = :reason, decided_at = now()
        WHERE  request_id = :r
    """), {"s": body.decision, "c": ctx["user"]["id"], "reason": body.reason, "r": request_id})

    if row["request_type"] == "submission.release" and body.decision == "rejected":     # closes a legacy draft (E99)
        try:
            session.execute(text("""
                UPDATE bank_disclosure_submissions
                SET    status = 'rejected', checker_user_id = :c, checker_at = now(), released_at = NULL
                WHERE  approval_request_id = :r
            """), {"c": ctx["user"]["id"], "r": request_id})
        except Exception as e:
            raise _not_applied(e) from e

    # Governed location changes: apply the mutation on approval (shares the exact same apply path
    # the direct edit uses, so an approved change is identical to a direct one). Audited within.
    applied = None
    if body.decision == "approved" and row["request_type"].startswith("supply."):
        from services.governance.location_governance import apply_location_change
        try:
            applied = apply_location_change(session, row["request_type"], row["payload"],
                                            actor_user_id=ctx["user"]["id"], org_id=org_id)
        except Exception as e:
            raise _not_applied(e) from e
    elif body.decision == "approved" and row["request_type"].startswith("config."):
        from services.governance.config_governance import apply_config_change
        try:
            applied = apply_config_change(session, row["request_type"], row["payload"],
                                          actor_user_id=ctx["user"]["id"], org_id=org_id)
        except Exception as e:
            raise _not_applied(e) from e
    # Filing approval: a filing.approve request clearing (or being sent back) drives the filing lifecycle.
    # 4-eyes is already enforced above (checker ≠ maker), so an approved filing is one a second pair of eyes signed.
    elif row["request_type"] == "filing.approve":
        from services.governance.filings import FilingError, mark_approved, mark_returned
        fid = (row["payload"] or {}).get("filing_id")
        try:
            if body.decision == "approved":
                applied = mark_approved(session, org_id, fid, ctx["user"]["id"], reason=body.reason)
            elif body.decision == "returned":
                applied = mark_returned(session, org_id, fid, ctx["user"]["id"], reason=body.reason)
            else:  # rejected
                applied = mark_returned(session, org_id, fid, ctx["user"]["id"], reason=body.reason, rejected=True)
        except FilingError as e:
            raise _not_applied(e) from e
    # Cell-level manual override on the final form: on approval it takes effect over the frozen snapshot;
    # 4-eyes (checker ≠ maker) is enforced above, so an approved override carries a second person's sign-off.
    # European ESG Template version: approved → published (the file distributors receive); otherwise rejected.
    elif row["request_type"] == "eet.publish":
        from services.eet.publication import EETError
        from services.eet.publication import apply_decision as apply_eet
        try:
            applied = apply_eet(session, org_id, row["payload"] or {}, body.decision, ctx["user"]["id"], body.reason)
        except EETError as e:
            raise _not_applied(e) from e
    elif row["request_type"] == "filing.cell_override":
        from services.governance.filing_overrides import apply_decision
        applied = apply_decision(session, org_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    # Forward-risk decision: on approval it becomes the standing call and (for actionable actions) spins a
    # Kanban card. 4-eyes (checker ≠ maker) is enforced above.
    elif row["request_type"] == "risk.decision":
        from services.intelligence.forward_decisions import apply_decision as apply_risk_decision
        applied = apply_risk_decision(session, org_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    # Provided datapoint (Lane 2): on attestation the customer/vendor value is signed off and may land in a
    # filing; 4-eyes (checker ≠ maker) is enforced above.
    # Use Tellumen's value for an asset fact instead of the client's (intake phase 3): the live value changes only now.
    # Lifting a legal hold on a filed report: only a second person may end it.
    elif row["request_type"] == "filing.legal_hold_lift":
        from services.governance.record_retention import apply_lift
        applied = apply_lift(session, org_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    # A reference data release (FAOSTAT crop production, E148): approved → its rows land in the store; otherwise it
    # closes unlanded. The maker reviewed the difference; the checker is the second operator.
    elif row["request_type"] == "reference.release_land":
        from services.reference.crop_releases import ReleaseError
        from services.reference.crop_releases import apply_decision as apply_release
        try:
            applied = apply_release(session, row["payload"] or {}, body.decision, ctx["user"]["id"], body.reason)
        except ReleaseError as e:
            raise _not_applied(e) from e
    # A batch of crop calibration runs (E162): approved → each publishes (fit, calibration row, recipe named); otherwise
    # the runs close unpublished. The platform's system account proposed it; the operator here is the reviewer.
    elif row["request_type"] == "calibration.publish":
        from services.calibration.publish import PublishError
        from services.calibration.publish import apply_decision as apply_calibration
        try:
            applied = apply_calibration(session, row["payload"] or {}, body.decision, ctx["user"]["id"], body.reason)
        except PublishError as e:
            raise _not_applied(e) from e
    elif row["request_type"] == "intake.conflict":
        from services.intake.conflicts import apply_decision as apply_conflict
        applied = apply_conflict(session, org_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    # Year-end close of an undertaking's period, or a closed period's value restated with its reason (four eyes above)
    # EUDR: the undertaking's status, and its risk assessment of a movement — four eyes above
    elif row["request_type"] == "eudr.status":
        from services.eudr.records import apply_status
        applied = apply_status(session, org_id, request_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    elif row["request_type"] == "eudr.risk":
        from services.eudr.records import apply_assessment
        applied = apply_assessment(session, org_id, request_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    elif row["request_type"] == "csrd.role":
        from services.governance.csrd_roles import apply_decision as apply_role
        applied = apply_role(session, org_id, request_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    elif row["request_type"] in ("period.close", "period.restate"):
        from services.governance.period_close import PeriodError
        from services.governance.period_close import apply_decision as apply_period
        try:
            applied = apply_period(session, org_id, request_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
        except PeriodError as e:
            raise _not_applied(e) from e
    elif row["request_type"] == "provided.datapoint":
        from services.governance.provided_data import attest as attest_provided
        applied = attest_provided(session, org_id, row["payload"] or {}, body.decision, ctx["user"]["id"])
    # Kanban task completion: on approval the task moves Review→Done, the mover (checker) named on the
    # 'moved' event — the platform's real 4-eyes (checker ≠ maker, enforced above), not a self-ticked
    # checklist item. Rejected/returned leaves the task in Review; nothing silently advances.
    # Customer data batch that failed an intake check: on approval it is imported from the stored file after every
    # check is re-run on those exact bytes; 4-eyes (checker ≠ maker) is enforced above.
    elif row["request_type"] == "intake.batch":
        from services.intake.pipeline import IntakeError
        from services.intake.pipeline import decide as decide_batch
        try:
            applied = decide_batch(session, org_id, (row["payload"] or {}).get("batch_id"), body.decision,
                                   ctx["user"]["id"], body.reason)
        except IntakeError as e:
            raise _not_applied(e) from e
    elif row["request_type"] == "task.complete" and body.decision == "approved":
        from services.governance.tasks import TaskError, _complete_via_approval
        payload = row["payload"] or {}
        try:
            applied = _complete_via_approval(session, org_id, payload.get("task_id"), ctx["user"]["id"],
                                             payload.get("note"))
        except TaskError as e:
            raise _not_applied(e) from e

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
