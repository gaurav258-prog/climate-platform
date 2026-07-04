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
    include=["services.tasks.hazard_tasks"],
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
)
