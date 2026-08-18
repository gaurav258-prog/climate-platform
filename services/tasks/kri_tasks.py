"""Scheduled KRI observation — the interval sweep behind detection lag.

Celery beat fires `kri.observe_sweep` hourly (see celery_app.beat_schedule). It evaluates every tenant's
KRIs and reconciles breach episodes (services.governance.kri_monitor.sweep), so a breach's onset is recorded
independently of whether anyone happens to open the dashboard — which is what makes detection/surface lag a
real measure — and a newly opened breach fires the kri.breached webhook on its own. Idempotent; no operator
action required.
"""
from __future__ import annotations

import logging

from services.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="kri.observe_sweep")
def kri_observe_sweep() -> dict:
    from core.db.session import get_session
    from services.governance.kri_monitor import sweep
    with get_session() as s:
        roll = sweep(s)
    if roll.get("opened") or roll.get("cleared"):
        logger.info("kri observe sweep: %s", roll)
    return roll
