"""Golden-source feeds refresh automatically — and a failed automated pull is caught, not hidden.

Guards the automation behind the freshness monitor: run_scheduled_refreshes() refreshes the auto-scheduled
feeds (live/proxy/partial) and skips the on-demand/planned/estimated ones; a hook that raises records a
'failed' event that surfaces as a pre-filing control. Requires PostgreSQL; self-cleaning.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.data import feeds

# A feed whose hook calls a live third-party endpoint (GVP WFS, World Bank, EU agri-food, Copernicus) can
# legitimately fail from a real outage on THEIR side even after our own retries — a live-network integration test
# hitting the real internet, not a bug in this codebase. The refresh records why it failed (E215): cause
# 'source_unreachable' when the error says the provider could not be reached or answered 502/503/504
# (services.data.feeds.source_unreachable), 'adapter_fault' otherwise. Only the provider's side is tolerated here;
# any other failure (a KeyError, a bad URL, a parsing bug, a missing key) is a real regression this test must catch.


_REPO = Path(__file__).resolve().parents[2]


def _checkout_state() -> dict | None:
    """Every changed or untracked-and-not-ignored path under data/ (where feeds land files), with a hash of its
    content (None when this is not a git checkout). Equal before and after a refresh = the refresh wrote nothing git
    tracks (E114). Scoped to data/ because the checkout is shared: code edited meanwhile is not a feed's doing."""
    if shutil.which("git") is None or not (_REPO / ".git").exists():
        return None
    out = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", "data"], cwd=_REPO,
                         capture_output=True, text=True, check=True).stdout
    state = {}
    for entry in filter(None, out.split("\0")):
        p = _REPO / entry[3:]
        state[entry] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
    return state


@pytest.mark.integration
def test_scheduler_refreshes_only_auto_feeds():
    before = _checkout_state()
    with get_session() as s:
        done = feeds.run_scheduled_refreshes(s, force=True)
    keys = {d["feed_key"] for d in done}
    # every auto feed refreshed…
    auto = {f["key"] for f in feeds.FEEDS if f["auto_refresh"]}
    assert auto and auto.issubset(keys)
    # …and no on-demand / planned / estimated feed was auto-refreshed (they don't self-refresh)
    not_auto = {f["key"] for f in feeds.FEEDS if not f["auto_refresh"]}
    assert not (keys & not_auto), "a non-auto feed was auto-refreshed — it should be on-demand/planned only"
    real_failures = [d for d in done if d["status"] != "refreshed" and d["cause"] != "source_unreachable"]
    assert not real_failures, f"refresh failure(s) on our side, a real regression: {real_failures}"
    # E114: a refresh lands its files under the gitignored live root (core/live_data.py), never on a tracked path
    after = _checkout_state()
    if before is not None:
        moved = {k for k in before.keys() | after.keys() if before.get(k, "∅") != after.get(k, "∅")}
        assert not moved, f"a feed refresh changed git-tracked data: {sorted(moved)}"


@pytest.mark.integration
def test_failed_auto_refresh_is_recorded_and_surfaces_as_a_control():
    key = "fire_thermal"   # a basis-invalidating auto feed
    try:
        feeds.register_refresh_hook(key, lambda s: (_ for _ in ()).throw(RuntimeError("FIRMS 503")))
        with get_session() as s:
            r = feeds.refresh_one(s, key)
            assert r["status"] == "failed" and r["cause"] == "adapter_fault"   # a message saying 503 is not an answer
            overdue = feeds.overdue_basis_feeds(s)
            assert any(f["key"] == key and f["status"] == "failed" for f in overdue), \
                "a failed automated refresh of a basis feed must surface as a pre-filing control"
    finally:
        feeds._REFRESH_HOOKS.pop(key, None)
        with get_session() as s:            # reset to a clean 'refreshed' state
            feeds.refresh_one(s, key)
            assert [f for f in feeds.feed_freshness(s) if f["key"] == key][0]["status"] != "failed"


@pytest.mark.integration
def test_a_providers_outage_is_recorded_as_theirs_and_still_surfaces_as_a_control():
    """E215: Copernicus answering '502 Bad Gateway' is the provider's side — recorded with cause source_unreachable and
    said so in the note — yet the basis is still not refreshed, so the pre-filing control still shows it."""
    import requests
    key = "fire_thermal"

    def outage(_s):
        r = requests.Response()
        r.status_code = 502
        raise requests.HTTPError("502 Server Error: Bad Gateway for url: https://example.invalid", response=r)
    try:
        feeds.register_refresh_hook(key, outage)
        with get_session() as s:
            r = feeds.refresh_one(s, key)
            assert r["status"] == "failed" and r["cause"] == "source_unreachable"
            assert r["note"].startswith("refresh failed: source unreachable (HTTPError)")
            row = s.execute(text("SELECT cause FROM feed_refresh_log WHERE refresh_id = CAST(:i AS uuid)"),
                            {"i": r["refresh_id"]}).scalar()
            assert row == "source_unreachable"
            assert any(f["key"] == key and f["status"] == "failed" for f in feeds.overdue_basis_feeds(s))
    finally:
        feeds._REFRESH_HOOKS.pop(key, None)
        with get_session() as s:
            assert feeds.refresh_one(s, key)["cause"] is None          # a success carries no cause


@pytest.mark.integration
def test_manual_override_still_works_and_is_actored():
    with get_session() as s:
        uid = s.execute(text("SELECT user_id FROM users LIMIT 1")).scalar()
        res = feeds.refresh_one(s, "reference_lei", actor_user_id=str(uid))
        assert res["status"] == "refreshed"
        row = s.execute(text("SELECT actor_user_id FROM feed_refresh_log "
                             "WHERE feed_key='reference_lei' ORDER BY seq DESC LIMIT 1")).scalar()
        assert str(row) == str(uid)         # a manual override records WHO did it (system refreshes are NULL)
