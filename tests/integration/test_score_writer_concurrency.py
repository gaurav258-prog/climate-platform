"""Two scoring jobs writing the same cell at the same moment must be serialised, not collide on the one-active-score
rule (ux_canonical_active_key). Proven without committing anything: writer 1 holds the cell; writer 2, with a short
lock timeout, must be made to WAIT (it times out) instead of racing ahead — and the wait is on the per-cell writer
lock, taken before the retire (the database's unique-index wait alone would still let it collide after writer 1
commits). Both transactions are rolled back."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import h3
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.db.session import get_session
from scripts.score_point_gridded_on_demand import _write_active_scores

pytestmark = pytest.mark.integration
CELL = h3.latlng_to_cell(-40.0, -130.0, 8)   # South Pacific: no real score lives here


def _rec():
    return [{"h3_cell": CELL, "risk_score": 0.1, "risk_bucket": "low", "shap_factors": json.dumps({"test": True})}]


def test_second_writer_waits_for_the_first():
    now = datetime.now(timezone.utc)
    with get_session() as s1, get_session() as s2:
        try:
            _write_active_scores(s1, "pollution", _rec(), "test", now)          # holds the cell until it ends
            free = s2.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:k))"),
                              {"k": f"canonical:pollution:{CELL}"}).scalar()
            assert free is False    # the cell is held by writer 1 for its whole transaction (the fix)
            s2.rollback()
            s2.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError, match="lock timeout"):
                _write_active_scores(s2, "pollution", _rec(), "test", now)
        finally:
            s2.rollback()
            s1.rollback()


def test_a_different_cell_is_not_blocked():
    now = datetime.now(timezone.utc)
    other = [{**_rec()[0], "h3_cell": h3.latlng_to_cell(-41.0, -131.0, 8)}]
    with get_session() as s1, get_session() as s2:
        try:
            _write_active_scores(s1, "pollution", _rec(), "test", now)
            s2.execute(text("SET LOCAL lock_timeout = '300ms'"))
            _write_active_scores(s2, "pollution", other, "test", now)          # no wait
        finally:
            s2.rollback()
            s1.rollback()
