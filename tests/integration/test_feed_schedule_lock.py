"""E178: a scheduled feed refresh never writes during a test run. The platform's own scheduler (Celery beat, or the
API's fallback ticker when the broker is away) staged a release for review while the gate ran, and the demo-data
guard read the new approval request as a leaking test. Now a scheduled tick runs only while it holds the
scheduled-refresh lock, and the suite's guard holds that lock for the whole run."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.config import engine
from services.data import feeds

pytestmark = pytest.mark.integration


def _held_elsewhere() -> bool:
    with engine.connect() as c:
        got = c.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": feeds.SCHEDULED_REFRESH_LOCK}).scalar()
        if got:
            c.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": feeds.SCHEDULED_REFRESH_LOCK})
        return not got


def test_a_scheduled_tick_waits_while_the_lock_is_held(session_rolled_back, monkeypatch):
    def refreshed(*a, **k):
        raise AssertionError("a scheduled tick refreshed while the lock was held")
    monkeypatch.setattr(feeds, "_refresh_due", refreshed)
    with engine.connect() as holder:                     # the suite's guard holds it already; hold it here too
        holder.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": feeds.SCHEDULED_REFRESH_LOCK})
        assert _held_elsewhere()
        assert feeds.run_scheduled_refreshes(session_rolled_back, force=False) == []
        holder.execute(text("SELECT pg_advisory_unlock_all()"))


def test_the_test_run_itself_holds_the_lock():
    import os
    if os.environ.get("TELLUMEN_SKIP_DB_GUARD") == "1":
        pytest.skip("the demo-data guard is bypassed in this run")
    assert _held_elsewhere()


def test_a_forced_refresh_is_an_operator_action_and_does_not_wait(session_rolled_back, monkeypatch):
    monkeypatch.setattr(feeds, "_refresh_due", lambda session, force: [{"feed_key": "x", "status": "refreshed"}])
    assert feeds.run_scheduled_refreshes(session_rolled_back, force=True) == [{"feed_key": "x", "status": "refreshed"}]
