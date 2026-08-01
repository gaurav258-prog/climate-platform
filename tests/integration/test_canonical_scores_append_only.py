"""canonical_scores is append-only — UPDATE and DELETE are blocked at the DB (audit App-pillar).

This is a load-bearing honesty invariant: a calibrated standing climatology must never be silently
retired or edited in place. The guarantee lives in DB triggers (prevent_update/prevent_delete), so the
regression test exercises the DB, not Python. It never inserts (rows are permanent by design) — it
attempts a self-assignment UPDATE and a DELETE on one existing row and asserts both raise, then rolls
back so nothing changes. Requires PostgreSQL.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import InternalError, OperationalError, DatabaseError

from core.db.session import get_session

_TRIGGER_ERRORS = (InternalError, OperationalError, DatabaseError)


@pytest.mark.integration
def test_update_is_blocked():
    with get_session() as s:
        ctid = s.execute(text("SELECT ctid FROM canonical_scores LIMIT 1")).scalar()
        assert ctid is not None, "no canonical_scores rows to test against"
        with pytest.raises(_TRIGGER_ERRORS):
            # a no-op self-assignment still fires the row-level BEFORE UPDATE trigger
            s.execute(text("UPDATE canonical_scores SET score_lane = score_lane WHERE ctid = :c"),
                      {"c": ctid})
        s.rollback()


@pytest.mark.integration
def test_delete_is_blocked():
    with get_session() as s:
        ctid = s.execute(text("SELECT ctid FROM canonical_scores LIMIT 1")).scalar()
        assert ctid is not None, "no canonical_scores rows to test against"
        with pytest.raises(_TRIGGER_ERRORS):
            s.execute(text("DELETE FROM canonical_scores WHERE ctid = :c"), {"c": ctid})
        s.rollback()


@pytest.mark.integration
def test_triggers_are_installed():
    with get_session() as s:
        names = set(s.execute(text(
            "SELECT tgname FROM pg_trigger WHERE tgrelid='canonical_scores'::regclass "
            "AND NOT tgisinternal")).scalars().all())
    assert {"prevent_update_canonical_scores", "prevent_delete_canonical_scores"} <= names
