"""Stale golden-source feeds are caught BEFORE they can taint a filing (audit T4, staleness layer).

A feed that drives an un-frozen filing (`invalidates_basis`) and is overdue must surface as a pre-filing
control so the operator refreshes it first. Requires PostgreSQL. Self-cleaning (feed_refresh_log is not WORM).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.data.feeds import basis_freshness_at, overdue_basis_feeds


@pytest.mark.integration
def test_overdue_basis_feed_is_detected_then_clears_on_refresh():
    # pick a basis-driving feed with a short cadence to make it easy to age past
    with get_session() as s:
        before = {f["key"] for f in overdue_basis_feeds(s)}
        # simulate a refresh older than the feed's cadence → overdue
        s.execute(text("INSERT INTO feed_refresh_log (feed_key, status, created_at) "
                       "VALUES ('flood', 'refreshed', now() - interval '5 days')"))
        s.commit()
    try:
        with get_session() as s:
            keys = {f["key"] for f in overdue_basis_feeds(s)}
            assert "flood" in keys, "an overdue basis feed was not surfaced as a pre-filing control"
            # and it must be recorded in the freshness stamp that goes into a frozen filing
            assert basis_freshness_at(s).get("flood") == "overdue"
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM feed_refresh_log WHERE feed_key='flood' "
                           "AND created_at < now() - interval '4 days'"))
            s.commit()
    # a fresh refresh clears it
    with get_session() as s:
        s.execute(text("INSERT INTO feed_refresh_log (feed_key, status) VALUES ('flood','refreshed')"))
        s.commit()
    try:
        with get_session() as s:
            assert "flood" not in {f["key"] for f in overdue_basis_feeds(s)}
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM feed_refresh_log WHERE feed_key='flood' "
                           "AND created_at > now() - interval '1 minute'"))
            s.commit()


@pytest.mark.integration
def test_freshness_stamp_only_covers_basis_feeds():
    with get_session() as s:
        stamp = basis_freshness_at(s)
    # reference-only feeds (don't invalidate a filing) must not be in the basis-freshness stamp
    assert "reference_lei" not in stamp and "atmosphere" not in stamp
    assert "climate_reanalysis" in stamp
