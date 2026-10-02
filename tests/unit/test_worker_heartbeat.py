"""Executor liveness is decided by one pure staleness rule: alive iff some heartbeat row is no older than 3 × the beat interval."""
from datetime import datetime, timedelta, timezone

from services.tasks.heartbeat import HEARTBEAT_INTERVAL_S, STALE_AFTER_S, is_alive, summarize

NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)


def test_stale_window_is_three_beats():
    assert HEARTBEAT_INTERVAL_S == 30
    assert STALE_AFTER_S == 3 * HEARTBEAT_INTERVAL_S == 90


def test_no_heartbeat_is_not_alive():
    assert is_alive(None, NOW) is False
    assert summarize([], NOW) == {"alive": False, "last_seen": None, "stale_after_s": STALE_AFTER_S, "workers": []}


def test_fresh_and_boundary_heartbeats_are_alive():
    assert is_alive(NOW - timedelta(seconds=1), NOW)
    assert is_alive(NOW - timedelta(seconds=STALE_AFTER_S), NOW)          # exactly the window: still alive


def test_older_than_window_is_stale():
    assert is_alive(NOW - timedelta(seconds=STALE_AFTER_S + 1), NOW) is False
    assert is_alive(NOW - timedelta(hours=3), NOW) is False


def test_naive_timestamps_are_read_as_utc():
    assert is_alive(NOW.replace(tzinfo=None) - timedelta(seconds=5), NOW)


def _row(worker, age_s, queue="celery"):
    return {"worker": worker, "queue": queue, "hostname": "h", "version": "0.1.0", "last_seen": NOW - timedelta(seconds=age_s)}


def test_any_fresh_executor_makes_the_fleet_alive():
    out = summarize([_row("celery@a", 400), _row("child:12:transmission.send", 10, "process")], NOW)
    assert out["alive"] is True
    assert [w["alive"] for w in out["workers"]] == [False, True]
    assert out["last_seen"] == NOW - timedelta(seconds=10)


def test_all_stale_executors_are_unavailable():
    out = summarize([_row("celery@a", 91), _row("celery@b", 3600)], NOW)
    assert out["alive"] is False
    assert out["last_seen"] == NOW - timedelta(seconds=91)          # the last time anyone was seen is still reported


def test_worker_state_word_follows_alive():
    from services.tasks.jobs import worker_state
    assert worker_state({"alive": True}) == "alive"
    assert worker_state({"alive": False}) == "unavailable"


def test_a_job_goes_to_the_worker_only_when_a_live_worker_names_it(monkeypatch):
    """E110: a worker started on older code beat 'alive' and refused a job added since, unseen. A job is sent to the
    worker only when a live worker named it at start; otherwise it runs in a child process on this code."""
    from services.tasks import jobs as J
    sent, spawned = [], []
    monkeypatch.setattr(J, "broker_reachable", lambda timeout=1.0: True)

    class _P:
        pid = 4242
        def __init__(self, target, args, name, daemon): spawned.append(args[0])
        def start(self): pass
    monkeypatch.setattr(J.mp, "get_context", lambda kind: type("C", (), {"Process": _P}))
    from services.tasks.celery_app import celery_app
    monkeypatch.setattr(celery_app, "send_task", lambda job, args: sent.append(job) or type("R", (), {"id": "t1"}))
    fresh = NOW.replace(tzinfo=None)

    def fleet(jobs):
        return {"alive": True, "workers": [{"worker": "w", "alive": True, "jobs": jobs, "last_seen": fresh}]}
    monkeypatch.setattr(J, "worker_status", lambda session=None: fleet(["eudr.read_plots"]))
    assert J.submit("eudr.read_plots", "org", [], None)["via"] == "celery" and sent == ["eudr.read_plots"]
    monkeypatch.setattr(J, "worker_status", lambda session=None: fleet(["intake.process"]))      # older code
    assert J.submit("eudr.read_plots", "org", [], None)["via"] == "process" and spawned == ["eudr.read_plots"]
    monkeypatch.setattr(J, "worker_status", lambda session=None: fleet(None))                    # names none
    assert J.submit("eudr.read_plots", "org", [], None)["via"] == "process" and sent == ["eudr.read_plots"]
