"""Published calibrations are flagged for re-validation once their training window is stale (audit T12).

The control surfaces drift risk (never silently retires a calibration). Requires PostgreSQL.
"""
from __future__ import annotations

import pytest

from core.db.session import get_session
from services.intelligence.revalidation import (
    overdue_calibrations, revalidation_status, REVALIDATION_HORIZON_YEARS,
)


@pytest.mark.integration
def test_stale_training_window_is_flagged():
    with get_session() as s:
        # far in the future: every published calibration is well past the horizon → all flagged
        future = overdue_calibrations(s, as_of_year=2100)
        assert future, "no published calibrations found to age-check"
        assert all(o["years_behind"] >= REVALIDATION_HORIZON_YEARS for o in future)
        # each carries the training-through year and tier so a human can act
        assert all({"commodity", "origin", "trained_through", "tier"} <= set(o) for o in future)


@pytest.mark.integration
def test_recent_window_is_not_flagged():
    from sqlalchemy import text
    with get_session() as s:
        # a reporting year at the newest training window: nothing is 3y stale yet
        max_bt = s.execute(text(
            "SELECT max(baseline_to) FROM v_sc_commodity_calibration "
            "WHERE calibration_tier IN ('ranged','backtested')")).scalar()
        assert max_bt is not None
        assert overdue_calibrations(s, as_of_year=int(max_bt)) == []


@pytest.mark.integration
def test_status_shape():
    with get_session() as s:
        st = revalidation_status(s, as_of_year=2100)
        assert st["horizon_years"] == REVALIDATION_HORIZON_YEARS
        assert st["overdue_count"] == len(st["overdue"]) and st["overdue_count"] > 0
