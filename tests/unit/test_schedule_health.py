"""Scheduled-job health (services/tasks/schedule_health.py): periods and the ok / overdue / failed / never_run rule."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from celery.schedules import crontab

from services.tasks.heartbeat import summarize
from services.tasks.schedule_health import evaluate, period_seconds

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def test_periods():
    assert period_seconds(300.0) == 300
    assert period_seconds(crontab(minute=0)) == 3600
    assert period_seconds(crontab(hour=6, minute=30)) == 86400
    assert period_seconds(crontab(hour=6, minute=0, day_of_week=1)) == 7 * 86400


def test_each_job_is_judged_against_its_own_period():
    e = [{"name": "sweep", "task": "t.sweep", "period_s": 300}, {"name": "daily", "task": "t.daily", "period_s": 86400},
         {"name": "new", "task": "t.new", "period_s": 3600}, {"name": "bad", "task": "t.bad", "period_s": 3600}]
    runs = {"t.sweep": {"last_finished_at": NOW - timedelta(minutes=11), "last_status": "ok"},     # > 2 × 5 min
            "t.daily": {"last_finished_at": NOW - timedelta(hours=20), "last_status": "ok"},
            "t.bad": {"last_finished_at": NOW - timedelta(minutes=5), "last_status": "failed", "last_error": "Boom"}}
    got = {j["name"]: j["status"] for j in evaluate(e, runs, NOW)}
    assert got == {"sweep": "overdue", "daily": "ok", "new": "never_run", "bad": "failed"}


def test_scheduler_heartbeat_never_counts_as_a_worker():
    # read_heartbeats excludes queue 'beat'; summarize of an empty executor list is not alive
    assert summarize([])["alive"] is False
