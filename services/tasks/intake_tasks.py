"""Intake sweeps (see celery_app.beat_schedule):
  intake.sweep_drop_folders   every 5 minutes — each finished file in every enabled channel runs through the intake
                              pipeline (services/intake/dropfolder.py)
  intake.observe_books        hourly — every organisation's asset facts, per source (services/intake/observations.py):
                              catches a fact written by any path, derives our values, reconciles"""
from __future__ import annotations

import logging

from services.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="intake.sweep_drop_folders")
def sweep_drop_folders() -> dict:
    from services.intake.dropfolder import sweep_all
    out = sweep_all()
    logger.info("drop-folder sweep: %s", out)
    return out


@celery_app.task(name="intake.observe_books")
def observe_books() -> dict:
    from core.db.session import get_session
    from services.intake.observations import sync_all
    with get_session() as s:
        out = sync_all(s)
    logger.info("observe books: %s organisation(s) changed", len(out))
    return {"orgs_changed": len(out)}
