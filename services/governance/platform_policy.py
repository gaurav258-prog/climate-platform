"""How many people must approve a platform change (E150) — the platform organisation's governed statement.

  2  a person proposes, another approves (four eyes between two people)
  1  the platform's system account proposes, with its evidence, and one person approves — stated when the organisation
     has a single approver; the approvals path still refuses a maker deciding their own request

Read here; changed only through set_human_approvers (an operator with reference.release_review, audited with the
reason). The system account (pipeline@system.tellumen.io) is disabled with no password: it can never sign in.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages

PLATFORM_ORG = "99999999-9999-4999-8999-999999999999"
SYSTEM_USER = "00000000-0000-4000-8000-0000000005e1"
# each action's customer name is a code of the message catalogue (core/messages.py)
ACTIONS = {"reference.release_land": "reference.release.approvers.release_land",
           "calibration.publish": "reference.release.approvers.calibration_publish"}


class PolicyError(ValueError):
    """A policy change refused — a code of the message catalogue with its values (core/errors.py UserError)."""

    def __init__(self, code: str, **params) -> None:
        self.code, self.params = code, params
        super().__init__(messages.label(code, **params))


def human_approvers(session: Session, action_key: str) -> int:
    n = session.execute(text("""SELECT human_approvers FROM approval_policy
                                WHERE org_id = CAST(:o AS uuid) AND action_key = :k"""),
                        {"o": PLATFORM_ORG, "k": action_key}).scalar()
    return int(n) if n is not None else 2          # no statement: two people (the safe reading)


def policies(session: Session) -> list[dict]:
    rows = {r["action_key"]: dict(r) for r in session.execute(text("""
        SELECT p.action_key, p.human_approvers, p.updated_at, u.email AS updated_by FROM approval_policy p
        LEFT JOIN users u ON u.user_id = p.updated_by
        WHERE p.org_id = CAST(:o AS uuid) AND p.action_key = ANY(:k)"""), {"o": PLATFORM_ORG, "k": list(ACTIONS)}).mappings()}
    return [{"action_key": k, **messages.render(code), **(rows.get(k) or {"human_approvers": 2})}
            for k, code in ACTIONS.items()]


def set_human_approvers(session: Session, action_key: str, n: int, actor_user_id: str, reason: str) -> dict:
    from api.services.rbac import write_audit
    if action_key not in ACTIONS:
        raise PolicyError("reference.release.error.unknown_rule")
    if n not in (1, 2):
        raise PolicyError("reference.release.error.approvers_count")
    why = (reason or "").strip()
    if len(why) < 10:
        raise PolicyError("reference.release.error.rule_note_required")
    before = human_approvers(session, action_key)
    session.execute(text("""
        INSERT INTO approval_policy (org_id, action_key, requires_approval, human_approvers, updated_at, updated_by)
        VALUES (CAST(:o AS uuid), :k, true, :n, now(), CAST(:u AS uuid))
        ON CONFLICT (org_id, action_key) WHERE org_id IS NOT NULL
        DO UPDATE SET human_approvers = EXCLUDED.human_approvers, updated_at = now(), updated_by = EXCLUDED.updated_by"""),
        {"o": PLATFORM_ORG, "k": action_key, "n": n, "u": actor_user_id})
    write_audit(session, org_id=PLATFORM_ORG, actor_user_id=actor_user_id, action="platform_policy.human_approvers",
                target_type="approval_policy", target_id=action_key, detail={"from": before, "to": n, "reason": why})
    return {"action_key": action_key, "human_approvers": n, "was": before}
