"""Regulatory task board — create, move, assign, and de-dupe by source. Requires PostgreSQL."""
from __future__ import annotations

import pytest
from sqlalchemy import text

import services.governance.tasks as T
from core.db.session import get_session

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
def test_attachments_add_list_get_delete():
    with get_session() as s:
        u = _actor(s)
        t = T.create_task(s, BANK_ORG, u, title="Attach evidence")
        tid = t["task_id"]
        a = T.add_attachment(s, BANK_ORG, tid, u, filename="notes.txt", content_type="text/plain", data=b"hello")
        assert a["size_bytes"] == 5
        items = T.list_attachments(s, BANK_ORG, tid)
        assert len(items) == 1 and items[0]["filename"] == "notes.txt"
        got = T.get_attachment(s, BANK_ORG, tid, a["attachment_id"])
        assert got["data"] == b"hello" and got["content_type"] == "text/plain"
        with pytest.raises(T.TaskError):
            T.add_attachment(s, BANK_ORG, tid, u, filename="", content_type=None, data=b"x")
        T.delete_attachment(s, BANK_ORG, tid, a["attachment_id"], u)
        assert T.list_attachments(s, BANK_ORG, tid) == []
        s.rollback()


@pytest.mark.integration
def test_comment_mentions_and_inbox():
    with get_session() as s:
        maker = _actor(s)
        target = str(s.execute(text("SELECT user_id FROM users WHERE email='approver@meridian.demo'")).scalar())
        t = T.create_task(s, BANK_ORG, maker, title="Clarify NACE mapping")
        tid = t["task_id"]
        # a comment mentioning a colleague creates an unread mention for them
        T.comment(s, BANK_ORG, tid, maker, "@Pieter please confirm", mentions=[target])
        inbox = T.my_mentions(s, BANK_ORG, target)
        assert any(m["task_id"] == tid for m in inbox)
        # you are never mentioned to yourself
        T.comment(s, BANK_ORG, tid, maker, "note to self @me", mentions=[maker])
        assert all(m["task_id"] != tid for m in T.my_mentions(s, BANK_ORG, maker))
        # opening the task clears the recipient's unread mentions on it
        T.mark_mentions_seen(s, BANK_ORG, tid, target)
        assert all(m["task_id"] != tid for m in T.my_mentions(s, BANK_ORG, target))
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
