"""Regulatory task board — create, move, assign, and de-dupe by source. Requires PostgreSQL."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
import services.governance.tasks as T

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _actor(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


@pytest.mark.integration
def test_create_move_assign_flow_and_events():
    with get_session() as s:
        u = _actor(s)
        t = T.create_task(s, BANK_ORG, u, title="Generate the XBRL", criticality="high")
        assert t["status"] == "todo" and t["criticality"] == "high"
        tid = t["task_id"]
        analyst = str(s.execute(text("SELECT user_id FROM users WHERE email='analyst@meridian.demo'")).scalar())
        # gate: a card can't enter Doing without an owner assigned
        with pytest.raises(T.TaskError):
            T.move_task(s, BANK_ORG, tid, u, "doing", ["ready"])
        t = T.assign_task(s, BANK_ORG, tid, u, analyst)
        assert t["assignee_user_id"] == analyst
        # gate: even with an owner, a gated forward move needs its checklist confirmed
        with pytest.raises(T.TaskError):
            T.move_task(s, BANK_ORG, tid, u, "doing")
        t = T.move_task(s, BANK_ORG, tid, u, "doing", ["inputs available"])
        assert t["status"] == "doing"
        # gate: Review needs the work recorded (a description) before it will accept the move
        with pytest.raises(T.TaskError):
            T.move_task(s, BANK_ORG, tid, u, "review", ["complete"])
        T.update_task(s, BANK_ORG, tid, u, description="Assembled the XBRL from the frozen snapshot.")
        t = T.move_task(s, BANK_ORG, tid, u, "review", ["complete and self-checked"])
        assert t["status"] == "review"
        # backward moves are free (no gate)
        t = T.move_task(s, BANK_ORG, tid, u, "doing")
        assert t["status"] == "doing"
        kinds = [e["kind"] for e in t["events"]]
        assert "created" in kinds and "moved" in kinds and "assigned" in kinds
        # the confirmed checklist is recorded on the activity log
        assert any(e["kind"] == "moved" and (e.get("note") or "").startswith("gate confirmed") for e in t["events"])
        s.rollback()


@pytest.mark.integration
def test_source_ref_dedupes():
    """Spinning a task from the same validation exception twice returns the same task, not a duplicate."""
    with get_session() as s:
        u = _actor(s)
        a = T.create_task(s, BANK_ORG, u, title="Fix coverage", source="validation", source_ref="full_coverage")
        b = T.create_task(s, BANK_ORG, u, title="Fix coverage (again)", source="validation", source_ref="full_coverage")
        assert a["task_id"] == b["task_id"]
        s.rollback()


@pytest.mark.integration
def test_board_groups_into_columns():
    with get_session() as s:
        b = T.board(s, BANK_ORG)
        assert [c["key"] for c in b["columns"]] == T.COLUMNS
        assert set(b["summary"]) == {"total", "overdue", "unassigned"}
        s.rollback()


@pytest.mark.integration
def test_bad_status_and_missing_title_refused():
    with get_session() as s:
        u = _actor(s)
        with pytest.raises(T.TaskError):
            T.create_task(s, BANK_ORG, u, title="   ")
        t = T.create_task(s, BANK_ORG, u, title="ok")
        with pytest.raises(T.TaskError):
            T.move_task(s, BANK_ORG, t["task_id"], u, "nonsense")
        s.rollback()
