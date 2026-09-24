"""Kanban task completion is REAL 4-eyes (2026-09-24 fix, independent Kanban review finding K1): the old
'Reviewed by a second person' checklist item was self-tickable — any single user could confirm their own
attestation and move a card straight to Done. Completion now goes through the platform's generic
approval_requests mechanism (the SAME maker!=checker DB CHECK every other 4-eyes action in this codebase
relies on) — a task can only reach 'done' as the side effect of a DIFFERENT user approving a real request.

Requires PostgreSQL. Non-polluting: each test rolls back its session on exit.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

import services.governance.tasks as T
from core.db.session import get_session

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _actor(s, email="admin@meridian.demo"):
    return str(s.execute(text("SELECT user_id FROM users WHERE email=:e"), {"e": email}).scalar())


def _task_in_review(s, u):
    t = T.create_task(s, BANK_ORG, u, title="File the XBRL")
    tid = t["task_id"]
    analyst = _actor(s, "analyst@meridian.demo")
    T.assign_task(s, BANK_ORG, tid, u, analyst)
    T.move_task(s, BANK_ORG, tid, u, "doing", ["inputs available"])
    T.update_task(s, BANK_ORG, tid, u, description="Assembled the XBRL from the frozen snapshot.")
    T.move_task(s, BANK_ORG, tid, u, "review", ["complete and self-checked"])
    return tid


@pytest.mark.integration
def test_direct_move_to_done_is_refused():
    """A raw move to 'done' — however the mover self-attests — is never allowed; there is no checklist path
    into Done any more, only the real approval."""
    with get_session() as s:
        u = _actor(s)
        tid = _task_in_review(s, u)
        with pytest.raises(T.TaskError, match="4-eyes approval"):
            T.move_task(s, BANK_ORG, tid, u, "done", ["reviewed by a second person", "recorded"])
        s.rollback()


@pytest.mark.integration
def test_request_completion_creates_a_real_approval_request():
    with get_session() as s:
        u = _actor(s)
        tid = _task_in_review(s, u)
        out = T.request_completion(s, BANK_ORG, tid, u, "Filed as bank_tcfd v3, accepted.")
        assert out["status"] == "review"  # stays in Review until approved
        assert out["pending_completion_request_id"]
        row = s.execute(text("""
            SELECT request_type, maker_user_id::text, status FROM approval_requests
            WHERE request_id = CAST(:r AS uuid)
        """), {"r": out["pending_completion_request_id"]}).mappings().first()
        assert row["request_type"] == "task.complete" and row["maker_user_id"] == u and row["status"] == "pending"
        s.rollback()


@pytest.mark.integration
def test_request_completion_needs_a_note_and_task_in_review():
    with get_session() as s:
        u = _actor(s)
        tid = _task_in_review(s, u)
        with pytest.raises(T.TaskError, match="Record what the outcome"):
            T.request_completion(s, BANK_ORG, tid, u, "   ")
        # not in Review yet
        t2 = T.create_task(s, BANK_ORG, u, title="Still in todo")
        with pytest.raises(T.TaskError, match="must be in Review"):
            T.request_completion(s, BANK_ORG, t2["task_id"], u, "done")
        s.rollback()


@pytest.mark.integration
def test_duplicate_completion_request_refused():
    with get_session() as s:
        u = _actor(s)
        tid = _task_in_review(s, u)
        T.request_completion(s, BANK_ORG, tid, u, "first request")
        with pytest.raises(T.TaskError, match="already pending"):
            T.request_completion(s, BANK_ORG, tid, u, "second request")
        s.rollback()


@pytest.mark.integration
def test_complete_via_approval_is_the_only_path_to_done_and_names_the_real_checker():
    """The internal function invoked by approvals.decide() — proves a DIFFERENT user's action is what
    actually lands the task in 'done', and the audit event names them, not the original mover."""
    with get_session() as s:
        maker = _actor(s, "admin@meridian.demo")
        checker = _actor(s, "approver@meridian.demo")
        tid = _task_in_review(s, maker)
        T.request_completion(s, BANK_ORG, tid, maker, "Filed and accepted.")
        out = T._complete_via_approval(s, BANK_ORG, tid, checker, "Filed and accepted.")
        assert out["status"] == "done"
        moved = [e for e in out["events"] if e["kind"] == "moved" and e["to"] == "done"]
        assert moved and moved[0]["actor"] != None
        # the event's actor is the CHECKER, not the original mover
        checker_name = s.execute(text("SELECT full_name FROM users WHERE user_id=CAST(:u AS uuid)"),
                                 {"u": checker}).scalar()
        assert moved[0]["actor"] == checker_name
        assert "4-eyes approved" in (moved[0]["note"] or "")
        s.rollback()


@pytest.mark.integration
def test_complete_via_approval_refuses_if_task_moved_away_from_review():
    """A stale completion request (task got dragged elsewhere while the approval sat pending) must not
    silently force the task back to Done."""
    with get_session() as s:
        maker = _actor(s, "admin@meridian.demo")
        checker = _actor(s, "approver@meridian.demo")
        tid = _task_in_review(s, maker)
        T.request_completion(s, BANK_ORG, tid, maker, "Filed and accepted.")
        T.move_task(s, BANK_ORG, tid, maker, "doing")   # dragged back before the checker acts
        with pytest.raises(T.TaskError, match="no longer in Review"):
            T._complete_via_approval(s, BANK_ORG, tid, checker, "Filed and accepted.")
        s.rollback()


@pytest.mark.integration
def test_full_http_flow_via_approvals_decide():
    """End-to-end through the real router: request-completion, then a DIFFERENT user decides via
    POST /v1/approvals/{id}/decide — the same endpoint every other 4-eyes action in this codebase uses."""
    from fastapi.testclient import TestClient
    from api.main import app
    client = TestClient(app, raise_server_exceptions=False)

    with get_session() as s:
        maker_id = _actor(s, "admin@meridian.demo")
        checker_id = _actor(s, "approver@meridian.demo")
        tid = _task_in_review(s, maker_id)
        s.commit()   # the HTTP layer uses its own session/connection

    try:
        maker_tok = client.post("/v1/auth/login", json={"email": "admin@meridian.demo", "password": "Demo!admin1"}).json()["access_token"]
        checker_tok = client.post("/v1/auth/login", json={"email": "approver@meridian.demo", "password": "Demo!approve1"}).json()["access_token"]

        r = client.post(f"/v1/reg-tasks/{tid}/request-completion",
                        json={"note": "Filed as bank_tcfd v4, accepted by the regulator."},
                        headers={"Authorization": f"Bearer {maker_tok}"})
        assert r.status_code == 201, r.text
        rid = r.json()["pending_completion_request_id"]
        assert rid

        # the maker cannot decide their own request — real 4-eyes, enforced by the same endpoint as everywhere else
        r_self = client.post(f"/v1/approvals/{rid}/decide", json={"decision": "approved"},
                             headers={"Authorization": f"Bearer {maker_tok}"})
        assert r_self.status_code == 422, r_self.text

        r2 = client.post(f"/v1/approvals/{rid}/decide", json={"decision": "approved"},
                         headers={"Authorization": f"Bearer {checker_tok}"})
        assert r2.status_code == 200, r2.text
        assert r2.json()["applied"]["status"] == "done"

        r3 = client.get(f"/v1/reg-tasks/{tid}", headers={"Authorization": f"Bearer {maker_tok}"})
        assert r3.json()["status"] == "done"
    finally:
        # regulatory_task_event is WORM (append-only, DB-trigger-enforced) — its rows are never deleted, same
        # as every other audit trail in this codebase. Cancel the task instead: it drops off the active board
        # (list_tasks excludes 'cancelled') while its real, accurate history stays on the record.
        with get_session() as s:
            s.execute(text("UPDATE regulatory_task SET status='cancelled' WHERE task_id = CAST(:t AS uuid)"), {"t": tid})
            s.commit()
