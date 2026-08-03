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
        t = T.move_task(s, BANK_ORG, t["task_id"], u, "doing")
        assert t["status"] == "doing"
        analyst = str(s.execute(text("SELECT user_id FROM users WHERE email='analyst@meridian.demo'")).scalar())
        t = T.assign_task(s, BANK_ORG, t["task_id"], u, analyst)
        assert t["assignee_user_id"] == analyst
        kinds = [e["kind"] for e in t["events"]]
        assert "created" in kinds and "moved" in kinds and "assigned" in kinds
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
