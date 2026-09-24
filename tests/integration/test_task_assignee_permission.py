"""A task can only be assigned to someone who can actually act on it (2026-09-24 fix, independent Kanban
review finding K5): assign_task() used to check only org membership — a card could be handed to a
read-only role that can never move, comment on, or complete it (every write action on a task is gated on
approvals.create). Meridian's real 'auditor' role is a genuine example, not a synthetic one: it's
deliberately read-only (admin.audit.view/oversight.view/reports.view only), and auditor@meridian.demo holds
ONLY that role — no analyst/approver overlap granting it approvals.create some other way.

Requires PostgreSQL. Non-polluting: each test rolls back its session on exit.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

import services.governance.tasks as T
from core.db.session import get_session

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _actor(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


def _user(s, email):
    return str(s.execute(text("SELECT user_id FROM users WHERE email=:e"), {"e": email}).scalar())


@pytest.mark.integration
def test_assigning_to_a_read_only_role_is_refused():
    with get_session() as s:
        u = _actor(s)
        t = T.create_task(s, BANK_ORG, u, title="Needs a real owner")
        auditor = _user(s, "auditor@meridian.demo")   # real role: reports.view only, no approvals.create
        with pytest.raises(T.TaskError, match="can't act on tasks"):
            T.assign_task(s, BANK_ORG, t["task_id"], u, auditor)
        s.rollback()


@pytest.mark.integration
def test_assigning_to_a_maker_role_still_works():
    with get_session() as s:
        u = _actor(s)
        t = T.create_task(s, BANK_ORG, u, title="Needs a real owner")
        analyst = _user(s, "analyst@meridian.demo")   # real role: has approvals.create
        out = T.assign_task(s, BANK_ORG, t["task_id"], u, analyst)
        assert out["assignee_user_id"] == analyst
        s.rollback()


@pytest.mark.integration
def test_create_task_with_an_unassignable_user_is_also_refused():
    """The same bug was ALSO reachable via create_task()'s own assignee_user_id param — it used to insert
    it directly, no validation at all, not even org membership."""
    with get_session() as s:
        u = _actor(s)
        auditor = _user(s, "auditor@meridian.demo")
        with pytest.raises(T.TaskError, match="can't act on tasks"):
            T.create_task(s, BANK_ORG, u, title="Pre-assigned at creation", assignee_user_id=auditor)
        s.rollback()


@pytest.mark.integration
def test_unassign_is_always_allowed():
    with get_session() as s:
        u = _actor(s)
        t = T.create_task(s, BANK_ORG, u, title="Needs a real owner",
                          assignee_user_id=_user(s, "analyst@meridian.demo"))
        out = T.assign_task(s, BANK_ORG, t["task_id"], u, None)
        assert out["assignee_user_id"] is None
        s.rollback()


@pytest.mark.integration
def test_members_endpoint_only_lists_assignable_users():
    """The picker itself must not even offer a colleague the server would then refuse."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT DISTINCT u.email FROM users u
            JOIN user_roles ur ON ur.user_id = u.user_id
            JOIN role_permissions rp ON rp.role_id = ur.role_id
            JOIN permissions p ON p.permission_id = rp.permission_id
            WHERE u.org_id = :o AND u.status = 'active' AND p.code = 'approvals.create'
        """), {"o": BANK_ORG}).scalars().all()
        assert "auditor@meridian.demo" not in rows
        assert "analyst@meridian.demo" in rows
