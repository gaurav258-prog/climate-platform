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


@celery_app.task(name="supervision.deadline_sweep")
def deadline_sweep() -> dict:
    return resolve("supervision.deadline_sweep")()


@celery_app.task(name="transmission.send", bind=True, max_retries=3, default_retry_delay=300)
def transmission_send(self, transmission_id: str) -> dict:
    out = resolve("transmission.send")(transmission_id)
    if out.get("status") == "failed":
        raise self.retry(countdown=300 * (self.request.retries + 1))
    return out


@celery_app.task(name="scoring.process_cells")
def scoring_process_cells(cell_coords: dict) -> dict:
    """Score newly located cells (every on-demand hazard) off the request path — the one entry every upload,
    intake and site-add uses through the jobs layer."""
    from services.scoring.on_demand import process_new_cells
    return process_new_cells({k: tuple(v) for k, v in cell_coords.items()})


@celery_app.task(name="calibration.run")
def calibration_run(sources: list | None = None) -> dict:
    """Re-run the calibration recipes reading the given yield sources (after a reviewed release lands, E162)."""
    return resolve("calibration.run")(sources)


@celery_app.task(name="calibration.refresh_weather")
def calibration_refresh_weather() -> dict:
    """Fetch new ERA5-Land months, rebuild the crop weather, re-run the calibrations (E163)."""
    return resolve("calibration.refresh_weather")()
