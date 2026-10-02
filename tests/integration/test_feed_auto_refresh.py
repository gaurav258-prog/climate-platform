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

# A feed whose hook calls a live third-party endpoint (GVP WFS, World Bank, EU agri-food) can legitimately
# fail from a real, transient outage/block on THEIR side even after our own retry-with-backoff (see
# scripts/fetch_gvp_catalogue.py) — that is a live-network integration test hitting the real internet, not a
# bug in this codebase. record_refresh() already captures exactly this: the failure note names the network
# exception. Recognize that specific, already-handled shape and don't hard-fail the test on it — but still
# hard-fail on anything else, since a status of 'failed' for a reason that ISN'T "their server is
# unreachable" (a KeyError, a bad URL, a parsing bug…) is a real regression this test must catch.
_NETWORK_UNREACHABLE_MARKERS = ("ConnectionError", "ConnectionAborted", "RemoteDisconnected", "Timeout",
                                "unreachable", "Connection aborted", "Max retries exceeded",
                                "upstream unavailable")   # a provider that kept refusing after our retries (imf_fx)


def _is_network_unreachable(note: str | None) -> bool:
    return bool(note) and any(m in note for m in _NETWORK_UNREACHABLE_MARKERS)


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
        notes = {r["feed_key"]: r["note"] for r in s.execute(text(
            "SELECT DISTINCT ON (feed_key) feed_key, note FROM feed_refresh_log "
            "WHERE feed_key = ANY(:ks) ORDER BY feed_key, created_at DESC"),
            {"ks": [d["feed_key"] for d in done]}).mappings().all()}
    keys = {d["feed_key"] for d in done}
    # every auto feed refreshed…
    auto = {f["key"] for f in feeds.FEEDS if f["auto_refresh"]}
    assert auto and auto.issubset(keys)
    # …and no on-demand / planned / estimated feed was auto-refreshed (they don't self-refresh)
    not_auto = {f["key"] for f in feeds.FEEDS if not f["auto_refresh"]}
    assert not (keys & not_auto), "a non-auto feed was auto-refreshed — it should be on-demand/planned only"
    real_failures = [d for d in done if d["status"] != "refreshed"
                     and not _is_network_unreachable(notes.get(d["feed_key"]))]
    assert not real_failures, f"non-network refresh failure(s), a real regression: {real_failures}"
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
