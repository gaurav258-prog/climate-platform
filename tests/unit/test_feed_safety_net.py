"""Golden-source safety net: overdue basis feeds are auto-refreshed on read, throttled, never hammered."""
import services.data.feeds as feeds


def test_ensure_basis_fresh_refreshes_overdue_and_throttles(monkeypatch):
    calls = []
    state = {"pass": 0}
    def fake_overdue(session):
        state["pass"] += 1
        if state["pass"] == 1:   # before: two overdue — one stale, one attempted 10 minutes ago (throttled)
            return [{"key": "fire_thermal", "name": "FIRMS", "days_since": 3.0},
                    {"key": "imagery", "name": "Sentinel", "days_since": 10 / 60 / 24}]
        return [{"key": "imagery", "name": "Sentinel", "days_since": 10 / 60 / 24}]   # after: only the throttled one
    monkeypatch.setattr(feeds, "overdue_basis_feeds", fake_overdue)
    monkeypatch.setattr(feeds, "refresh_one", lambda s, k, actor_user_id=None: calls.append(k) or {"status": "refreshed"})
    r = feeds.ensure_basis_fresh(session=None, min_retry_hours=1.0)
    assert calls == ["fire_thermal"]                 # refreshed the stale one, NOT the one tried 10 min ago
    assert r["attempted"] == ["fire_thermal"]
    assert [f["key"] for f in r["overdue"]] == ["imagery"]


def test_ensure_basis_fresh_noop_when_all_fresh(monkeypatch):
    monkeypatch.setattr(feeds, "overdue_basis_feeds", lambda s: [])
    monkeypatch.setattr(feeds, "refresh_one", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not be called")))
    assert feeds.ensure_basis_fresh(session=None) == {"attempted": [], "overdue": []}
