"""Two guards on the worker, after a crash loop ran for two days unseen (E166).

What happened: the worker was started with Celery's default pool, which FORKS a child per slot. On macOS a forked child
segfaults the moment it opens a downloaded netCDF file (xarray → netCDF4/HDF5 initialised in the parent before the
fork). The broker then re-delivered the job (task_acks_late + task_reject_on_worker_lost), the next child crashed the
same way, and so on — about 85 deliveries per job, 36,000 in all, each one a fresh Copernicus request.

  1. FORK-FREE POOL. The worker runs the 'threads' pool by configuration (celery_app.py), and refuse_forking_pool
     stops a worker that is started on a forking pool anyway (`--pool=prefork` on a command line, an old run script).
     Raster reads already run in their own spawned process (services/geo/raster_sampler.py); xarray serialises its
     netCDF reads across threads with its own lock.
  2. DELIVERY CAP. Late acknowledgement exists so a job whose worker dies is run again, not lost. That is right for a
     worker killed by a restart and wrong for a job that itself kills the worker: GuardedTask counts each delivery of
     a job in Redis, and the delivery after MAX_DELIVERIES is not run — the job fails with TaskAbandoned (recorded in
     job_runs like any failure) and its on_abandon hook closes whatever was waiting on it.
"""
from __future__ import annotations

import logging
from typing import Optional

from celery import Task

logger = logging.getLogger(__name__)

MAX_DELIVERIES = 3                  # a job whose worker died this many times is not run a fourth time
_COUNT_TTL_S = 7 * 24 * 3600        # a re-delivery can come days later if the worker was down meanwhile
_KEY = "tellumen:deliveries:{}"
FORK_FREE_POOLS = ("threads", "solo")


class TaskAbandoned(RuntimeError):
    """The job killed its worker MAX_DELIVERIES times; it is failed, not run again."""


# ── 1. fork-free pool ───────────────────────────────────────────────────────────────────────────────────────────

def pool_name(pool_cls) -> str:
    """The configured pool as a name: a setting string ('threads'), an import path, or the pool class itself.
    Matched by path, never imported — importing every pool would pull in eventlet/gevent."""
    from celery.concurrency import ALIASES
    if isinstance(pool_cls, str):
        path = ALIASES.get(pool_cls, pool_cls)
    else:
        path = f"{pool_cls.__module__}:{pool_cls.__qualname__}"
    return next((alias for alias, p in ALIASES.items() if p == path), path)


def refuse_forking_pool(sender=None, **_) -> None:
    """worker_init: a worker on any pool but a fork-free one does not start."""
    name = pool_name(sender.pool_cls)
    if name not in FORK_FREE_POOLS:
        raise SystemExit(f"worker refused: pool {name!r} forks a child per slot, and a forked child segfaults on "
                         f"netCDF/HDF5 reads (E166). Start it with --pool=threads (the configured default).")


# ── 2. delivery cap ─────────────────────────────────────────────────────────────────────────────────────────────
_redis = None


def _client():
    global _redis
    if _redis is None:
        import redis

        from core.config import settings
        _redis = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    return _redis


def count_delivery(task_id: str) -> int:
    """This delivery's number for the job (1 = first). 0 when the count cannot be kept — the job then runs:
    the cap stops a loop, it never blocks work because Redis blinked."""
    try:
        r = _client()
        n = int(r.incr(_KEY.format(task_id)))
        r.expire(_KEY.format(task_id), _COUNT_TTL_S)
        return n
    except Exception as e:
        logger.warning("delivery of %s not counted: %s", task_id, e)
        return 0


def clear_deliveries(task_id: str) -> None:
    try:
        _client().delete(_KEY.format(task_id))
    except Exception as e:
        logger.warning("delivery count of %s not cleared: %s", task_id, e)


class GuardedTask(Task):
    """Base of every task (celery_app task_cls). A job that returns or raises is finished and its count cleared;
    only a job whose worker DIED keeps its count, so only a worker-killing job reaches the cap."""

    def on_abandon(self, args: tuple, kwargs: dict) -> None:
        """Close whatever is waiting on the job (a lookup row, a queued run). Default: nothing waits."""

    def __call__(self, *args, **kwargs):
        task_id: Optional[str] = getattr(self.request, "id", None)
        if task_id and not getattr(self.request, "is_eager", False):
            n = count_delivery(task_id)
            if n > MAX_DELIVERIES:
                clear_deliveries(task_id)
                logger.error("job %s[%s] abandoned: its worker died on each of %d deliveries",
                             self.name, task_id, MAX_DELIVERIES)
                try:
                    self.on_abandon(args, kwargs)
                except Exception as e:   # closing the waiter must not hide the abandonment itself
                    logger.warning("on_abandon of %s failed: %s", self.name, e)
                raise TaskAbandoned(f"worker died on each of {MAX_DELIVERIES} deliveries — not run again")
            try:
                return super().__call__(*args, **kwargs)
            finally:
                clear_deliveries(task_id)
        return super().__call__(*args, **kwargs)
