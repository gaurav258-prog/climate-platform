"""Is the timed work actually happening? Scheduler liveness + the last run of every scheduled job.

Before this, a stopped scheduler (celery beat) was invisible: the drop-folder sweep, feed refreshes and daily sweeps
simply never ran, and nothing said so. Now:
  * the scheduler process beats into worker_heartbeat under queue 'beat' — kept apart from worker liveness, so a
    running scheduler never makes a stopped worker look alive (and vice versa);
  * the worker records every task's start / finish / failure in job_runs (task signals);
  * schedule_status() compares each beat_schedule entry with its last finished run: a job not finished within two
    of its periods is OVERDUE (scheduler stopped, worker stopped, or the job keeps failing), one whose last run
    failed is FAILED — with the error.
"""
from __future__ import annotations

import logging
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

BEAT_QUEUE = "beat"
_started: dict[str, float] = {}


# ── worker side: record every task run ──────────────────────────────────────────────────────────────────────────

def _record(sql: str, params: dict) -> None:
    try:
        from core.db.session import get_session
        with get_session() as s:
            s.execute(text(sql), params)
            s.commit()
    except Exception as e:  # recording must never break the job itself
        logger.warning("job run not recorded: %s", e)


def on_task_prerun(task_id=None, task=None, **_) -> None:
    _started[task_id] = time.monotonic()
    _record("""INSERT INTO job_runs (task_name, last_started_at, last_status, n_runs) VALUES (:n, now(), 'running', 1)
               ON CONFLICT (task_name) DO UPDATE SET last_started_at = now(), last_status = 'running',
                                                   n_runs = job_runs.n_runs + 1""", {"n": task.name})


def on_task_postrun(task_id=None, task=None, state=None, **_) -> None:
    ms = int(1000 * (time.monotonic() - _started.pop(task_id, time.monotonic())))
    if state == "FAILURE":   # on_task_failure has recorded it with the error
        return
    _record("""UPDATE job_runs SET last_finished_at = now(), last_status = 'ok', last_error = NULL, last_duration_ms = :ms
               WHERE task_name = :n""", {"n": task.name, "ms": ms})


def on_task_failure(task_id=None, exception=None, sender=None, **_) -> None:
    ms = int(1000 * (time.monotonic() - _started.pop(task_id, time.monotonic())))
    _record("""UPDATE job_runs SET last_finished_at = now(), last_status = 'failed', last_duration_ms = :ms,
                                  last_error = :e, n_failures = n_failures + 1 WHERE task_name = :n""",
            {"n": sender.name, "ms": ms, "e": f"{type(exception).__name__}: {exception}"[:500]})


# ── scheduler side: one heartbeat for the beat process ─────────────────────────────────────────────────────────
_beat = None


def on_beat_init(**_) -> None:
    global _beat
    from services.tasks.heartbeat import Heartbeater
    _beat = Heartbeater(f"beat@{socket.gethostname()}", BEAT_QUEUE).start()
    logger.info("scheduler heartbeat started")


# ── read side ──────────────────────────────────────────────────────────────────────────────────────────────────

def period_seconds(schedule) -> float:
    """How often a beat entry fires: a number of seconds, or — for a crontab — the gap between its next two firings,
    found by walking minutes against the crontab's own field sets (no reliance on scheduler internals)."""
    if isinstance(schedule, (int, float)):
        return float(schedule)
    if isinstance(schedule, timedelta):
        return schedule.total_seconds()
    key = repr(schedule)
    if key not in _PERIODS:
        _PERIODS[key] = _crontab_period(schedule)
    return _PERIODS[key]


_PERIODS: dict[str, float] = {}


def _crontab_period(c) -> float:
    def fires(dt: datetime) -> bool:
        return (dt.minute in c.minute and dt.hour in c.hour and dt.isoweekday() % 7 in c.day_of_week
                and dt.day in c.day_of_month and dt.month in c.month_of_year)
    t0 = datetime(2026, 1, 5, tzinfo=timezone.utc)          # a fixed Monday: the period does not depend on today
    hits = []
    for m in range(0, 60 * 24 * 62):                          # up to two months ahead
        dt = t0 + timedelta(minutes=m)
        if fires(dt):
            hits.append(dt)
            if len(hits) == 2:
                return (hits[1] - hits[0]).total_seconds()
    return 86400.0 * 31


def evaluate(entries: list[dict], runs: dict[str, dict], now: Optional[datetime] = None) -> list[dict]:
    """Pure: each scheduled job → ok | overdue | failed | never_run, judged against its own period."""
    now = now or datetime.now(timezone.utc)
    out = []
    for e in entries:
        r = runs.get(e["task"]) or {}
        last = r.get("last_finished_at")
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if r.get("last_status") == "failed":
            status = "failed"
        elif last is None:
            status = "never_run"
        elif (now - last).total_seconds() > 2 * e["period_s"]:
            status = "overdue"
        else:
            status = "ok"
        out.append({**e, "status": status, "last_finished_at": last.isoformat() if last else None,
                    "last_status": r.get("last_status"), "last_error": r.get("last_error"),
                    "n_runs": r.get("n_runs", 0), "n_failures": r.get("n_failures", 0)})
    return out


def schedule_status(session=None) -> dict:
    """{scheduler: {alive, last_seen}, jobs: [...], n_problems}. A job that has never run is listed as such but not
    counted as a problem (it may be new); a scheduler that is not alive is the problem signal in that case."""
    from services.tasks.celery_app import celery_app
    from services.tasks.heartbeat import is_alive
    entries = [{"name": k, "task": v["task"], "period_s": period_seconds(v["schedule"])}
               for k, v in (celery_app.conf.beat_schedule or {}).items()]

    def _read(s):
        runs = {r["task_name"]: dict(r) for r in s.execute(text("SELECT * FROM job_runs")).mappings().all()}
        beat = s.execute(text("SELECT last_seen FROM worker_heartbeat WHERE queue = :q ORDER BY last_seen DESC LIMIT 1"),
                         {"q": BEAT_QUEUE}).scalar()
        return runs, beat
    if session is not None:
        runs, beat = _read(session)
    else:
        from core.db.session import get_session
        with get_session() as s:
            runs, beat = _read(s)
    jobs = evaluate(entries, runs)
    problems = [j for j in jobs if j["status"] in ("overdue", "failed")]
    return {"scheduler": {"alive": is_alive(beat), "last_seen": beat.isoformat() if beat else None},
            "jobs": jobs, "n_problems": len(problems)}
