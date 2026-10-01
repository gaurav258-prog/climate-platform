"""EUDR jobs (services.tasks.jobs): eudr.read_plots — each plot's satellite reading, kept (services/eudr/reading.py)."""
from __future__ import annotations

from typing import Optional

from services.tasks.celery_app import celery_app


@celery_app.task(name="eudr.read_plots")
def read_plots(org_id: str, plot_ids: list[str], user_id: Optional[str], treecover_min_pct: Optional[int] = None,
               point_radius_m: Optional[float] = None) -> dict:
    from services.eudr.reading import run_job
    return run_job(org_id, plot_ids, user_id, treecover_min_pct, point_radius_m)
