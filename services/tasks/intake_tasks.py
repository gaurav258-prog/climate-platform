"""Drop-folder sweep: Celery beat fires `intake.sweep_drop_folders` every 5 minutes (see celery_app.beat_schedule).
Each finished file in every enabled channel runs through the intake pipeline (services/intake/dropfolder.py)."""
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
