"""Supervision jobs on the worker: shadow-book projections and the geography priors behind the Tier-1 band.

Celery beat rebuilds the priors daily; feeds.refresh_due also enqueues a rebuild right after any golden-source
feed actually lands, so the band never lags a scoring refresh. Both tasks call the same functions the
in-process fallback runs (services.tasks.jobs).
"""
from __future__ import annotations

from services.tasks.celery_app import celery_app
from services.tasks.jobs import resolve


@celery_app.task(name="supervision.project_cells")
def project_cells(cells: list) -> dict:
    return resolve("supervision.project_cells")(list(cells))


@celery_app.task(name="supervision.rebuild_geo_priors")
def rebuild_geo_priors() -> dict:
    return resolve("supervision.rebuild_geo_priors")()
