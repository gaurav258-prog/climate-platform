"""Celery task: drain the email outbox.

The durable backstop for outbound notification email (task @mentions today). The comment endpoint already
delivers immediately in an in-process BackgroundTask; this periodic sweep guarantees delivery even if the API
restarted before that ran, and retries anything left 'pending' / 'failed' (e.g. a transient SMTP outage).
Runs in the separate Celery worker process, so SMTP work never touches the API.

Run the worker + beat alongside the API:
    .venv/bin/celery -A services.tasks.celery_app worker --loglevel=info
    .venv/bin/celery -A services.tasks.celery_app beat   --loglevel=info
"""
from __future__ import annotations

from services.tasks.celery_app import celery_app
from services.notifications import mailer


@celery_app.task(name="emails.drain_outbox")
def drain_outbox() -> dict:
    return mailer.drain_outbox(limit=500)
