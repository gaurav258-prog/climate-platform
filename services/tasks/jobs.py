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
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

JOBS: dict[str, str] = {
    "supervision.project_cells": "services.supervision.projection:project_cells_now",
    "supervision.rebuild_geo_priors": "services.supervision.geo_prior:rebuild_all",
    "supervision.deadline_sweep": "services.supervision.deadlines:sweep_all",
    "transmission.send": "services.transmission.service:send",
    "controls.test_sweep": "services.governance.controls:sweep_all",
    "scoring.process_cells": "services.scoring.on_demand:process_new_cells",
}


def resolve(job: str) -> Callable[..., Any]:
    if job not in JOBS:
        raise KeyError(f"unknown job {job!r}; known: {sorted(JOBS)}")
    mod, fn = JOBS[job].split(":")
    return getattr(importlib.import_module(mod), fn)


def _run_in_child(job: str, args: tuple) -> None:  # pragma: no cover — runs in the child
    """The child is an executor too: it heartbeats for as long as it runs, so a job it holds reads as alive and a
    job left 'queued' after it is gone reads as unavailable — the same rule as the Celery worker."""
    import os

    from services.tasks.heartbeat import Heartbeater
    beat = Heartbeater(f"child:{os.getpid()}:{job}", "process").start()
    try:
        resolve(job)(*args)
    except Exception as e:
        logging.getLogger(__name__).error("job %s failed in fallback child: %s", job, e)
    finally:
        beat.stop()


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


def worker_status(session=None) -> dict:
    """The one read of executor liveness: {alive, last_seen, stale_after_s, executor, workers}.
    `executor` says which path submit() would take now ('celery' when the broker answers, else 'process');
    `alive` is decided from heartbeat rows alone, so the child-process path is judged by the same rule."""
    from services.tasks.heartbeat import read_heartbeats, summarize
    executor = "celery" if broker_reachable() else "process"
    try:
        if session is not None:
            rows = read_heartbeats(session)
        else:
            from core.db.session import get_session
            with get_session() as s:
                rows = read_heartbeats(s)
    except Exception as e:
        logger.warning("worker heartbeat unreadable: %s", e)
        rows = []
    out = summarize(rows)
    out["last_seen"] = out["last_seen"].isoformat() if out["last_seen"] else None
    for w in out["workers"]:
        w["last_seen"] = w["last_seen"].isoformat() if w["last_seen"] else None
    return {**out, "executor": executor}


def worker_state(status: Optional[dict] = None) -> str:
    """'alive' | 'unavailable' — the word a queued job carries."""
    return "alive" if (status or worker_status())["alive"] else "unavailable"


def submit(job: str, *args: Any) -> dict:
    """→ {"via": "celery"|"process", "id": ..., "worker_state": "alive"|"unavailable"}.
    Never raises on transport trouble: falls back to a process. A job handed to Celery carries the worker's live
    state so the caller can say "worker unavailable" at once; a child process is spawned right here, so it is alive."""
    resolve(job)   # fail fast on a typo, before anything is queued
    if broker_reachable():
        try:
            from services.tasks.celery_app import celery_app
            r = celery_app.send_task(job, args=list(args))
            return {"via": "celery", "id": r.id, "worker_state": worker_state()}
        except Exception as e:
            logger.warning("could not enqueue %s on the worker (%s) — running in a child process", job, e)
    ctx = mp.get_context("spawn")
    p = ctx.Process(target=_run_in_child, args=(job, tuple(args)), name=f"job-{job}", daemon=True)
    p.start()
    return {"via": "process", "id": p.pid, "worker_state": "alive"}
