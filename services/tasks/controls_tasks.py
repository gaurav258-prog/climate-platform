"""Reporting control register sweep.

Celery beat fires `controls.test_sweep` daily (see celery_app.beat_schedule). It tests every tenant's controls and
records the outcomes, so operating effectiveness accrues without anyone opening the register.
"""
from __future__ import annotations

import logging

from services.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="controls.test_sweep")
def controls_test_sweep() -> dict:
    from core.db.session import get_session
    from services.governance.controls import sweep_all
    with get_session() as s:
        roll = sweep_all(s)
    logger.info("controls test sweep: %s", roll)
    return roll
