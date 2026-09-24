"""A task's filing_id is a REAL coupling, not decorative (2026-09-24 fix, independent Kanban review finding
K4): moving a filing-linked task into Review now runs the SAME validate_filing() the filing-generation gate
itself uses — a self-ticked "validation was run" checkbox is no longer the only thing standing behind that
claim.

Requires PostgreSQL. Non-polluting: each test rolls back its session on exit, on a throwaway future period
so it never collides with a real filing.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

import services.governance.tasks as T
from core.db.session import get_session
from services.governance.report_snapshots import create_snapshot

BANK_ORG = "11111111-1111-4111-8111-111111111111"
FUTURE_PERIOD = "2098-12-31"   # distinct from test_filing_lifecycle.py's own throwaway period


def _actor(s):
    return str(s.execute(text("SELECT user_id FROM users WHERE email='admin@meridian.demo'")).scalar())


def _real_draft_filing(s, u):
    """A genuine, frozen, passing filing — same recipe as test_filing_lifecycle.py."""
    snap = create_snapshot(s, BANK_ORG, "bank_tcfd", u)
    fid = s.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
        VALUES (:o, 'bank_tcfd', :pe, 'FY2098', 'draft', :snap, :u) RETURNING filing_id
    """), {"o": BANK_ORG, "pe": FUTURE_PERIOD, "snap": snap["snapshot_id"], "u": u}).scalar()
    return str(fid)


def _unsnapshotted_filing(s, u):
    """A filing with NO frozen snapshot behind it — validate_filing()'s very first check (snapshot_frozen)
    fails, guaranteeing a real blocking error to prove the gate actually reads it."""
    fid = s.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by)
        VALUES (:o, 'bank_tcfd', :pe, 'FY2098b', 'draft', NULL, :u) RETURNING filing_id
    """), {"o": BANK_ORG, "pe": "2097-12-31", "u": u}).scalar()
    return str(fid)


@pytest.mark.integration
def test_task_with_no_filing_link_is_unaffected():
    with get_session() as s:
        u = _actor(s)
        t = T.create_task(s, BANK_ORG, u, title="No filing here")
        T.assign_task(s, BANK_ORG, t["task_id"], u, u)
        T.move_task(s, BANK_ORG, t["task_id"], u, "doing", ["ready"])
        T.update_task(s, BANK_ORG, t["task_id"], u, description="Some work.")
        out = T.move_task(s, BANK_ORG, t["task_id"], u, "review", ["complete"])
        assert out["status"] == "review"
        s.rollback()


@pytest.mark.integration
def test_task_linked_to_a_passing_filing_moves_to_review():
    with get_session() as s:
        u = _actor(s)
        fid = _real_draft_filing(s, u)
        t = T.create_task(s, BANK_ORG, u, title="File the TCFD disclosure", filing_id=fid)
        T.assign_task(s, BANK_ORG, t["task_id"], u, u)
        T.move_task(s, BANK_ORG, t["task_id"], u, "doing", ["ready"])
        T.update_task(s, BANK_ORG, t["task_id"], u, description="Assembled from the frozen snapshot.")
        out = T.move_task(s, BANK_ORG, t["task_id"], u, "review", ["validation checked"])
        assert out["status"] == "review"
        s.rollback()


@pytest.mark.integration
def test_task_linked_to_a_failing_filing_is_blocked_with_the_real_reason():
    """The genuine finding: this used to be a self-tick with zero server verification — a task could reach
    Review claiming 'validation was run' for a filing that has never even been frozen."""
    with get_session() as s:
        u = _actor(s)
        fid = _unsnapshotted_filing(s, u)
        t = T.create_task(s, BANK_ORG, u, title="File the TCFD disclosure", filing_id=fid)
        T.assign_task(s, BANK_ORG, t["task_id"], u, u)
        T.move_task(s, BANK_ORG, t["task_id"], u, "doing", ["ready"])
        T.update_task(s, BANK_ORG, t["task_id"], u, description="Claims it's ready, but the filing is unfrozen.")
        with pytest.raises(T.TaskError, match="blocking validation errors"):
            # even with the checklist ticked, the SERVER'S OWN read of the filing must independently agree
            T.move_task(s, BANK_ORG, t["task_id"], u, "review", ["validation checked (falsely)"])
        s.rollback()


@pytest.mark.integration
def test_dangling_filing_link_does_not_crash_the_gate():
    """A filing_id pointing at a filing the gate can't find in THIS org (regulatory_task.filing_id is a plain
    FK to regulatory_filing, not org-scoped, so this is reachable) must never crash the move — it's a link
    integrity edge case, not a validation failure to block on."""
    with get_session() as s:
        u = _actor(s)
        other_org = s.execute(text(
            "SELECT org_id::text FROM organizations WHERE org_id <> :o LIMIT 1"), {"o": BANK_ORG}).scalar()
        other_fid = s.execute(text("""
            INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, created_by)
            VALUES (CAST(:o AS uuid), 'sfdr_pai', '2096-12-31', 'FY2096-other-org', 'draft', NULL) RETURNING filing_id
        """), {"o": other_org}).scalar()
        t = T.create_task(s, BANK_ORG, u, title="Stale filing link")
        s.execute(text("UPDATE regulatory_task SET filing_id = CAST(:f AS uuid) WHERE task_id = CAST(:t AS uuid)"),
                 {"f": str(other_fid), "t": t["task_id"]})
        T.assign_task(s, BANK_ORG, t["task_id"], u, u)
        T.move_task(s, BANK_ORG, t["task_id"], u, "doing", ["ready"])
        T.update_task(s, BANK_ORG, t["task_id"], u, description="Work done.")
        out = T.move_task(s, BANK_ORG, t["task_id"], u, "review", ["complete"])   # must not raise
        assert out["status"] == "review"
        s.rollback()
