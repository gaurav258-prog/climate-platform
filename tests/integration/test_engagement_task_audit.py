"""A supervision-engagement thread drives its linked entity task's status as a real, audited event
(2026-09-24 fix, independent Kanban review finding K2): this used to be a raw UPDATE regulatory_task with
NO regulatory_task_event row at all — the WORM audit trail's append-only guarantee was real for the Kanban
UI's own move_task() path but silently incomplete for this one (live DB confirmed: 86/97 non-initial-status
tasks had zero 'moved' events). Both the task's creation (raised by a supervisor) and every status sync it
gets from the engagement thread must now leave a genuine audit row.

Requires PostgreSQL. Non-polluting: each test rolls back its session on exit.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.supervision import engagement as E

REGULATOR_ORG = "88888888-8888-4888-8888-888888888888"   # EU Banking Supervisor (demo)
BANK_ORG = "11111111-1111-4111-8111-111111111111"          # Meridian Bank (demo), supervised by it


def _regulator_user(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@supervisor.demo'")).scalar())


def _entity_user(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


def _events(s, task_id):
    return s.execute(text("""
        SELECT kind, from_val, to_val, note, actor_user_id FROM regulatory_task_event
        WHERE task_id = CAST(:t AS uuid) ORDER BY created_at
    """), {"t": task_id}).mappings().all()


@pytest.mark.integration
def test_raising_a_request_logs_the_linked_task_creation():
    with get_session() as s:
        reg_user = _regulator_user(s)
        req = E.create(s, regulator_org_id=REGULATOR_ORG, supervised_org_id=BANK_ORG, kind="information_request",
                       title="Confirm exposure methodology", body="Please confirm.", raised_by=reg_user)
        tid = req["entity_task_id"]
        assert tid, "the request should have spun a real linked task"
        evs = _events(s, tid)
        created = [e for e in evs if e["kind"] == "created"]
        assert created, "the task's own creation must be in its audit trail, not invisible"
        assert created[0]["actor_user_id"] is None   # a cross-org system event, not a fake single user
        assert "system:supervision_engagement" in (created[0]["note"] or "")
        s.rollback()


@pytest.mark.integration
def test_entity_responding_logs_a_real_moved_event():
    with get_session() as s:
        reg_user = _regulator_user(s)
        entity_user = _entity_user(s)
        req = E.create(s, regulator_org_id=REGULATOR_ORG, supervised_org_id=BANK_ORG, kind="information_request",
                       title="Confirm exposure methodology", body="Please confirm.", raised_by=reg_user)
        tid = req["entity_task_id"]

        E.add_message(s, req["request_id"], side="entity", author_id=entity_user,
                      body="Confirmed, methodology attached.", status_to="responded")

        task = s.execute(text("SELECT status FROM regulatory_task WHERE task_id = CAST(:t AS uuid)"), {"t": tid}).mappings().first()
        assert task["status"] == "review"   # entity responding maps to Review, per the existing mapping

        evs = _events(s, tid)
        moved = [e for e in evs if e["kind"] == "moved"]
        assert moved, "the status sync must leave a real 'moved' event — this was the exact K2 gap"
        assert moved[-1]["from_val"] == "todo" and moved[-1]["to_val"] == "review"
        assert "system:supervision_engagement" in (moved[-1]["note"] or "")
        assert "Mara Admin" in (moved[-1]["note"] or "") or "admin@meridian.demo" in (moved[-1]["note"] or "")
        s.rollback()


@pytest.mark.integration
def test_supervisor_closing_logs_the_move_to_done():
    with get_session() as s:
        reg_user = _regulator_user(s)
        entity_user = _entity_user(s)
        req = E.create(s, regulator_org_id=REGULATOR_ORG, supervised_org_id=BANK_ORG, kind="information_request",
                       title="Confirm exposure methodology", body="Please confirm.", raised_by=reg_user)
        tid = req["entity_task_id"]
        E.add_message(s, req["request_id"], side="entity", author_id=entity_user, body="Confirmed.", status_to="responded")
        E.add_message(s, req["request_id"], side="supervisor", author_id=reg_user, body="Accepted, closing.", status_to="closed")

        task = s.execute(text("SELECT status FROM regulatory_task WHERE task_id = CAST(:t AS uuid)"), {"t": tid}).mappings().first()
        assert task["status"] == "done"

        evs = _events(s, tid)
        moves = [e for e in evs if e["kind"] == "moved"]
        assert len(moves) == 2   # todo->review, then review->done — every hop recorded, not just the last one
        assert moves[-1]["to_val"] == "done"
        s.rollback()


@pytest.mark.integration
def test_message_with_no_status_change_does_not_touch_the_task():
    """A plain thread message (no status_to) must not fabricate a task event."""
    with get_session() as s:
        reg_user = _regulator_user(s)
        req = E.create(s, regulator_org_id=REGULATOR_ORG, supervised_org_id=BANK_ORG, kind="information_request",
                       title="Confirm exposure methodology", body="Please confirm.", raised_by=reg_user)
        tid = req["entity_task_id"]
        before = len(_events(s, tid))
        E.add_message(s, req["request_id"], side="entity", author_id=_entity_user(s), body="Just a note, no status change.")
        after = len(_events(s, tid))
        assert after == before
        s.rollback()
