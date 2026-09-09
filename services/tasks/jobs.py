"""Heavy work never runs inside the API process.

`submit(job, *args)` hands a registered job to the Celery worker when the broker is reachable, and otherwise to a
freshly spawned child process — the same isolation the raster sampler gives reads. Either way the request thread
returns at once and a crash in the job cannot take the API down. Jobs are named, registered here, and resolved
by dotted path, so the Celery task and the fallback run exactly the same function.
"""
from __future__ import annotations

import importlib
import logging
import multiprocessing as mp
from typing import Any, Callable

logger = logging.getLogger(__name__)

JOBS: dict[str, str] = {
    "supervision.project_cells": "services.supervision.projection:project_cells_now",
    "supervision.rebuild_geo_priors": "services.supervision.geo_prior:rebuild_all",
    "supervision.deadline_sweep": "services.supervision.deadlines:sweep_all",
    "transmission.send": "services.transmission.service:send",
}


def resolve(job: str) -> Callable[..., Any]:
    if job not in JOBS:
        raise KeyError(f"unknown job {job!r}; known: {sorted(JOBS)}")
    mod, fn = JOBS[job].split(":")
    return getattr(importlib.import_module(mod), fn)


def _run_in_child(job: str, args: tuple) -> None:  # pragma: no cover — runs in the child
    try:
        resolve(job)(*args)
    except Exception as e:
        logging.getLogger(__name__).error("job %s failed in fallback child: %s", job, e)


def broker_reachable(timeout: float = 1.0) -> bool:
    import socket
    from urllib.parse import urlparse

    from core.config import settings
    try:
        u = urlparse(settings.REDIS_URL)
        with socket.create_connection((u.hostname or "localhost", u.port or 6379), timeout=timeout):
            return True
    except OSError:
        return False


def submit(job: str, *args: Any) -> dict:
    """→ {"via": "celery"|"process", "id": ...}. Never raises on transport trouble: falls back to a process."""
    resolve(job)   # fail fast on a typo, before anything is queued
    if broker_reachable():
        try:
            from services.tasks.celery_app import celery_app
            r = celery_app.send_task(job, args=list(args))
            return {"via": "celery", "id": r.id}
        except Exception as e:
            logger.warning("could not enqueue %s on the worker (%s) — running in a child process", job, e)
    ctx = mp.get_context("spawn")
    p = ctx.Process(target=_run_in_child, args=(job, tuple(args)), name=f"job-{job}", daemon=True)
    p.start()
    return {"via": "process", "id": p.pid}
