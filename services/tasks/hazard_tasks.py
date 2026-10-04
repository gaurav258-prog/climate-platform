"""
Celery task wrappers around the existing gridded on-demand scorer functions.

Deliberately a thin wrapper layer, not @celery_app.task decorators bolted
directly onto scripts/score_*.py's functions: those scripts stay callable
directly (by backtests, by direct test invocation) without importing Celery
at all. Only this module knows a task queue exists.

No automatic retry-on-exception here, deliberately: each scorer already has
its own try/except that marks the public_lookups row 'failed' and re-raises
on any error (see run_flood_lookup etc.). Adding a Celery-level retry on top
of that would create a real correctness wrinkle — a transient failure marks
'failed', then a successful retry would flip it back to 'done', so a client
polling in between could briefly see a wrong terminal state. celery_app.py's
task_acks_late + task_reject_on_worker_lost already give the durability this
migration is actually for (a worker CRASHING mid-task re-queues the job) —
that's a different, safe case from the function itself raising an exception.
A job that crashes its worker on EVERY delivery is failed after a few (E166):
LookupTask then marks its lookup row 'failed', so the client stops polling.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from scripts.score_drought_on_demand import run_drought_lookup
from scripts.score_heat_on_demand import run_heat_lookup
from scripts.score_point_gridded_on_demand import (
    run_flood_lookup,
    run_pollution_lookup,
    run_wildfire_lookup,
)

from .celery_app import celery_app
from .worker_guard import GuardedTask


class LookupTask(GuardedTask):
    """An abandoned lookup job ends its lookup row 'failed' — the same terminal state the scorer writes on an error."""

    def on_abandon(self, args: tuple, kwargs: dict) -> None:
        lookup_id = args[0] if args else kwargs.get("lookup_id")
        if not lookup_id:
            return
        from core.db.session import get_session
        with get_session() as s:
            s.execute(text("UPDATE public_lookups SET status='failed', completed_at=:now "
                           "WHERE lookup_id=:id AND status='computing'"),
                      {"now": datetime.now(timezone.utc), "id": lookup_id})
            s.commit()


@celery_app.task(name="hazard.flood", base=LookupTask)
def flood_task(lookup_id: str, lat: float, lon: float) -> None:
    run_flood_lookup(lookup_id, lat, lon)


@celery_app.task(name="hazard.pollution", base=LookupTask)
def pollution_task(lookup_id: str, lat: float, lon: float) -> None:
    run_pollution_lookup(lookup_id, lat, lon)


@celery_app.task(name="hazard.wildfire", base=LookupTask)
def wildfire_task(lookup_id: str, lat: float, lon: float) -> None:
    run_wildfire_lookup(lookup_id, lat, lon)


@celery_app.task(name="hazard.heat_acute", base=LookupTask)
def heat_acute_task(lookup_id: str, lat: float, lon: float) -> None:
    run_heat_lookup(lookup_id, lat, lon)


@celery_app.task(name="hazard.drought", base=LookupTask)
def drought_task(lookup_id: str, lat: float, lon: float) -> None:
    run_drought_lookup(lookup_id, lat, lon)


# hazard_type -> Celery task, mirrors GRIDDED_ON_DEMAND_SCORERS' shape exactly
# so api/routers/lookup.py's dispatch loop barely changes.
HAZARD_TASKS = {
    "flood": flood_task, "pollution": pollution_task, "wildfire": wildfire_task,
    "heat_acute": heat_acute_task, "drought": drought_task,
}
