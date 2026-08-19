"""Scheduled golden-source refresh — the automation behind the freshness monitor.

Celery beat fires `feeds.refresh_due` hourly (see celery_app.beat_schedule); the task refreshes only the
feeds actually DUE by their own cadence, records each result (refreshed / failed) to feed_refresh_log with
no actor (system), and lets a failure surface as a pre-filing control. No operator action required.
"""
from __future__ import annotations

import logging

from services.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="feeds.refresh_due")
def refresh_due_feeds() -> dict:
    from core.db.session import get_session
    from services.data.feeds import run_scheduled_refreshes
    with get_session() as s:
        done = run_scheduled_refreshes(s, force=False)
    n_ok = sum(1 for d in done if d.get("status") == "refreshed")
    n_fail = sum(1 for d in done if d.get("status") == "failed")
    if n_fail:
        logger.warning("scheduled feed refresh: %d refreshed, %d FAILED (%s)",
                       n_ok, n_fail, [d["feed_key"] for d in done if d.get("status") == "failed"])
    return {"refreshed": n_ok, "failed": n_fail, "feeds": [d["feed_key"] for d in done]}
