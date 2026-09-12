"""Pending 4-eyes requests whose policy is switched off — flagged and withdrawn, never silently decidable.

When an org switches an action's approval rule off (or narrows it — material fields, value threshold), any
request still waiting in the queue for that action was raised under a rule that no longer exists. Leaving it
decidable is dishonest (a checker would "approve" something the matrix no longer governs); applying it on the
switch is worse (the admin flipping the matrix may be the maker — the toggle would become a self-approval).

Rule, one mechanism for every governed action: after a policy change, re-run the SAME gate the submission
ran (`needs_approval` semantics + the value threshold) against each pending request of that action. Those the
new policy no longer covers are closed with status `withdrawn`, cause `policy_no_longer_requires_approval`,
a reason naming who switched the policy and when, and an audit row naming the policy switch as the trigger.
The change is NOT applied — the maker re-submits it and it applies directly under their own name, audited.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from api.services.rbac import write_audit

POLICY_OFF_CAUSE = "policy_no_longer_requires_approval"
AUDIT_ACTION = "approval.withdrawn_by_policy"


def changed_fields_of(request_type: str, payload: dict | None) -> list[str] | None:
    """The fields a request changes, as the submit gate saw them. Deletes have none (None)."""
    p = payload or {}
    if request_type.endswith(".delete"):
        return None
    if request_type.startswith("supply."):
        return list((p.get("changes") or {}).keys())
    if request_type.startswith("config."):
        return [k for k in p.keys() if not k.startswith("_")]
    return list(p.keys())


def still_requires_approval(policy: dict, request_type: str, payload: dict | None) -> bool:
    """Pure re-run of the submit gate against a (possibly changed) policy.
    policy = {requires_approval, material_fields, threshold_eur?}."""
    if not policy.get("requires_approval"):
        return False
    thr = policy.get("threshold_eur")
    if thr is not None:                                  # value-threshold actions (risk.decision)
        value = (payload or {}).get("value_eur")
        if value is not None:
            return float(value) >= float(thr)
        return True                                      # unknown value → stays governed (conservative)
    if request_type.endswith(".delete"):
        return True
    mats = list(policy.get("material_fields") or [])
    changed = changed_fields_of(request_type, payload)
    if not mats:
        return bool(changed)
    return any(f in mats for f in (changed or []))


def withdrawal_reason(label: str, switched_by: str | None, switched_at: str) -> str:
    who = switched_by or "an administrator"
    return (f"Policy no longer requires approval — '{label}' was switched to direct by {who} on {switched_at}. "
            "The change was NOT applied; re-submit it and it applies directly.")


def _policy(session: Session, org_id: str, action_key: str) -> dict:
    row = session.execute(text("""
        SELECT requires_approval, material_fields, threshold_eur FROM approval_policy
        WHERE action_key = :a AND (org_id = :o OR org_id IS NULL)
        ORDER BY org_id NULLS LAST LIMIT 1
    """), {"a": action_key, "o": org_id}).mappings().first()
    if not row:
        return {"requires_approval": False, "material_fields": [], "threshold_eur": None}
    return {"requires_approval": bool(row["requires_approval"]), "material_fields": list(row["material_fields"] or []),
            "threshold_eur": float(row["threshold_eur"]) if row["threshold_eur"] is not None else None}


def withdraw_moot_requests(session: Session, *, org_id: str, action_key: str, actor_user_id: str,
                           label: str) -> list[str]:
    """After a policy change: withdraw every pending request of this action the new policy no longer governs.
    Returns the withdrawn request ids. Caller commits."""
    policy = _policy(session, org_id, action_key)
    pending = session.execute(text("""
        SELECT request_id, payload FROM approval_requests
        WHERE org_id = :o AND request_type = :t AND status = 'pending'
    """), {"o": org_id, "t": action_key}).mappings().all()
    moot = [r for r in pending if not still_requires_approval(policy, action_key, r["payload"])]
    if not moot:
        return []
    who = session.execute(text("SELECT email FROM users WHERE user_id = CAST(:u AS uuid)"), {"u": actor_user_id}).scalar()
    when = session.execute(text("SELECT to_char(now() AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') || ' UTC'")).scalar()
    reason = withdrawal_reason(label, who, when)
    ids = [str(r["request_id"]) for r in moot]
    session.execute(text("""
        UPDATE approval_requests
        SET    status = 'withdrawn', withdrawn_cause = :c, reason = :reason, decided_at = now()
        WHERE  request_id = ANY(CAST(:ids AS uuid[])) AND status = 'pending'
    """), {"c": POLICY_OFF_CAUSE, "reason": reason, "ids": ids})
    if action_key == "risk.decision":                     # the proposed decision is withdrawn with its request
        session.execute(text("""
            UPDATE risk_decision SET status = 'withdrawn'
            WHERE org_id = :o AND status = 'proposed' AND approval_request_id = ANY(CAST(:ids AS uuid[]))
        """), {"o": org_id, "ids": ids})
    for r in moot:
        write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action=AUDIT_ACTION,
                    target_type="approval", target_id=str(r["request_id"]),
                    detail={"request_type": action_key, "cause": POLICY_OFF_CAUSE, "applied": False,
                            "trigger": {"action": "approval_policy.update", "action_key": action_key,
                                        "requires_approval": policy["requires_approval"],
                                        "material_fields": policy["material_fields"],
                                        "threshold_eur": policy["threshold_eur"]}})
    return ids
