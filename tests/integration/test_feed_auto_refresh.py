"""Golden-source feeds refresh automatically — and a failed automated pull is caught, not hidden.

Guards the automation behind the freshness monitor: run_scheduled_refreshes() refreshes the auto-scheduled
feeds (live/proxy/partial) and skips the on-demand/planned/estimated ones; a hook that raises records a
'failed' event that surfaces as a pre-filing control. Requires PostgreSQL; self-cleaning.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.data import feeds


@pytest.mark.integration
def test_scheduler_refreshes_only_auto_feeds():
    with get_session() as s:
        done = feeds.run_scheduled_refreshes(s, force=True)
    keys = {d["feed_key"] for d in done}
    # every auto feed refreshed…
    auto = {f["key"] for f in feeds.FEEDS if f["auto_refresh"]}
    assert auto and auto.issubset(keys)
    # …and no on-demand / planned / estimated feed was auto-refreshed (they don't self-refresh)
    not_auto = {f["key"] for f in feeds.FEEDS if not f["auto_refresh"]}
    assert not (keys & not_auto), "a non-auto feed was auto-refreshed — it should be on-demand/planned only"
    assert all(d["status"] == "refreshed" for d in done)


@pytest.mark.integration
def test_failed_auto_refresh_is_recorded_and_surfaces_as_a_control():
    key = "fire_thermal"   # a basis-invalidating auto feed
    try:
        feeds.register_refresh_hook(key, lambda s: (_ for _ in ()).throw(RuntimeError("FIRMS 503")))
        with get_session() as s:
            r = feeds.refresh_one(s, key)
            assert r["status"] == "failed"
            overdue = feeds.overdue_basis_feeds(s)
            assert any(f["key"] == key and f["status"] == "failed" for f in overdue), \
                "a failed automated refresh of a basis feed must surface as a pre-filing control"
    finally:
        feeds._REFRESH_HOOKS.pop(key, None)
        with get_session() as s:            # reset to a clean 'refreshed' state
            feeds.refresh_one(s, key)
            assert [f for f in feeds.feed_freshness(s) if f["key"] == key][0]["status"] != "failed"


@pytest.mark.integration
def test_manual_override_still_works_and_is_actored():
    with get_session() as s:
        uid = s.execute(text("SELECT user_id FROM users LIMIT 1")).scalar()
        res = feeds.refresh_one(s, "reference_lei", actor_user_id=str(uid))
        assert res["status"] == "refreshed"
        row = s.execute(text("SELECT actor_user_id FROM feed_refresh_log "
                             "WHERE feed_key='reference_lei' ORDER BY created_at DESC LIMIT 1")).scalar()
        assert str(row) == str(uid)         # a manual override records WHO did it (system refreshes are NULL)
