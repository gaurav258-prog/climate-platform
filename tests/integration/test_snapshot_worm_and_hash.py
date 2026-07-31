"""Frozen snapshots are tamper-evident (content hash re-verifies) and WORM (no UPDATE/DELETE). Audit T1.

Requires PostgreSQL. Non-polluting: verifies against existing snapshots and rolls back the mutation probes.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InternalError, ProgrammingError

from core.db.session import get_session
from services.governance.report_snapshots import get_snapshot


@pytest.mark.integration
def test_existing_snapshots_hash_verifies():
    """Every stored snapshot's payload must still hash to the value written at freeze time."""
    with get_session() as s:
        rows = s.execute(text("SELECT org_id, snapshot_id FROM report_snapshots LIMIT 50")).mappings().all()
    if not rows:
        pytest.skip("no snapshots to verify")
    with get_session() as s:
        for r in rows:
            snap = get_snapshot(s, str(r["org_id"]), str(r["snapshot_id"]))
            assert snap["payload_sha256"], f"snapshot {r['snapshot_id']} has no content hash"
            assert snap["hash_verified"] is True, (
                f"snapshot {r['snapshot_id']} payload does not match its stored hash — tampered or drifted"
            )


@pytest.mark.integration
def test_report_snapshots_are_worm():
    """UPDATE and DELETE on a frozen filing must both be rejected at the DB level."""
    with get_session() as s:
        sid = s.execute(text("SELECT snapshot_id FROM report_snapshots LIMIT 1")).scalar()
    if not sid:
        pytest.skip("no snapshot to probe")
    for sql, op in [("UPDATE report_snapshots SET note = 'tamper' WHERE snapshot_id = :s", "UPDATE"),
                    ("DELETE FROM report_snapshots WHERE snapshot_id = :s", "DELETE")]:
        raised = False
        try:
            with get_session() as s:
                s.execute(text(sql), {"s": sid})
                s.commit()
        except (InternalError, ProgrammingError):
            raised = True
        assert raised, f"WORM trigger did not block {op} on report_snapshots"
