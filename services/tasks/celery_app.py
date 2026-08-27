"""
Celery app for the gridded on-demand hazard jobs — the durability upgrade from
FastAPI BackgroundTasks flagged (and deliberately deferred) since Phase 2 of the
any-address lookup: "Celery/SQS+Redis is the correct upgrade path if this gets
real traffic — not built here, flagged not silently assumed away."

What this fixes: a job survives an API server restart (Redis persists the queue;
a separate worker process, not the API process, executes tasks) and gets Celery's
built-in retry/observability. What this does NOT fix: the external Copernicus
CDS/ADS and NASA FIRMS queue times themselves — those are the other side's
latency, not something any internal task-queue choice changes.

Run the worker separately from the API process:
    .venv/bin/celery -A services.tasks.celery_app worker --loglevel=info
"""
from __future__ import annotations

from celery import Celery

from core.config import settings

celery_app = Celery(
    "tellumen_hazard_jobs",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    # Without this, `celery -A services.tasks.celery_app worker` never imports
    # hazard_tasks.py, so none of its @celery_app.task decorators run and the
    # worker starts with an empty [tasks] list — confirmed live, a real bug,
    # not a hypothetical caveat.
    include=["services.tasks.hazard_tasks", "services.tasks.feed_refresh_tasks", "services.tasks.email_tasks",
             "services.tasks.decision_tasks", "services.tasks.kri_tasks", "services.tasks.reg_scan_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Jobs are CDS/FIRMS-fetch-bound (network I/O), not CPU-bound — a modest
    # per-worker concurrency lets several hazards progress in parallel without
    # pretending we can make the external service itself respond faster.
    worker_concurrency=4,
    task_acks_late=True,        # only ack after the task actually finishes — a
                                 # worker crash mid-job re-queues it, not silently drops it
    task_reject_on_worker_lost=True,
    # Publishing must FAIL FAST, never block a web request: if the broker is unreachable (e.g. Redis down),
    # a .delay() call should raise in ~2s and be swallowed by request_async_drain, not retry for 15s+. The
    # durable outbox + beat sweep already guarantee eventual delivery, so a dropped enqueue is harmless here.
    task_publish_retry=False,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
)

# Golden-source feeds refresh AUTOMATICALLY — no operator has to click. Celery beat runs the sweep every
# hour; the task itself only refreshes feeds actually DUE by their own cadence (daily/monthly/…), so this
# is cheap and each source lands on its own clock. Run beat alongside the worker:
#   celery -A services.tasks.celery_app beat
from celery.schedules import crontab  # noqa: E402

celery_app.conf.beat_schedule = {
    "refresh-due-golden-source-feeds": {
        "task": "feeds.refresh_due",
        "schedule": crontab(minute=0),   # top of every hour; the task refreshes only what's due
    },
    # Deliver queued notification email (task @mentions). The comment endpoint delivers immediately in-process;
    # this sweep is the durable retry backstop — every 2 minutes, sends only what's still pending/failed.
    "drain-email-outbox": {
        "task": "emails.drain_outbox",
        "schedule": 120.0,   # seconds
    },
    # Re-check the decision watchlist daily — re-scores every 'monitor' watch that's due, escalates further
    # deterioration, and alerts the watcher. The task itself filters to due watches, so this is cheap.
    "recheck-decision-watchlist": {
        "task": "decisions.recheck_watchlist",
        "schedule": crontab(hour=6, minute=30),   # once a day, early
    },
    # Observe every tenant's KRIs hourly so a breach's ONSET is recorded independently of dashboard visits —
    # the basis of an honest detection lag, and the trigger for the kri.breached webhook.
    "kri-observe-sweep": {
        "task": "kri.observe_sweep",
        "schedule": crontab(minute=0),   # top of every hour
    },
    # Scan EUR-Lex (Cellar SPARQL) daily for legal-date changes to the tracked frameworks — keeps the
    # regulatory outlook's dates verified live and surfaces detected changes for review.
    "scan-eurlex-daily": {
        "task": "reg.scan_eurlex",
        "schedule": crontab(hour=5, minute=15),   # once a day, early
    },
}
