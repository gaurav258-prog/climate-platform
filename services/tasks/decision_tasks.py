"""Scheduled re-check of the decision watchlist — the automation behind a 'monitor' decision.

Celery beat fires `decisions.recheck_watchlist` daily; the task re-scores only the watches actually DUE by
their review date (across all orgs), escalates any that have deteriorated further, and lets each escalation
raise its own alert (notify the watcher + a webhook). No operator action required.
"""
from __future__ import annotations

import logging

from services.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="decisions.recheck_watchlist")
def recheck_watchlist() -> dict:
    from core.db.session import get_session
    from services.intelligence.forward_decisions import recheck_watchlist as recheck
    with get_session() as s:
        escalated = recheck(s, org_id=None, due_only=True)
    if escalated:
        logger.warning("watchlist re-check: %d exposure(s) escalated (%s)",
                       len(escalated), [e["entity_name"] for e in escalated])
    return {"escalated": len(escalated)}
