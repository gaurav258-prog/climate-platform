"""One heartbeat mechanism for every job executor.

Design decision — a timer thread inside the executor process, NOT a beat-scheduled task and NOT task start/finish:
  * task start/finish only proves the worker is alive when it already has work — exactly the moment nobody asks;
    an idle worker would look dead, a dead worker with a queued job would look no different.
  * a beat-scheduled heartbeat task needs the separate `celery beat` process; with beat stopped a healthy worker
    would report unavailable. Liveness must be a property of the executor alone.
The Celery worker starts a `Heartbeater` on `worker_ready` and clears its row on `worker_shutdown`; the fallback
child process (broker unreachable) runs one for the duration of its job. Both write the same `worker_heartbeat`
row every HEARTBEAT_INTERVAL_S; `alive` = a row seen within STALE_AFTER_S = 3 × the interval (30 s → 90 s).
"""
from __future__ import annotations

import logging
import socket
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 30
STALE_AFTER_S = 3 * HEARTBEAT_INTERVAL_S      # 90 s: two missed beats plus the third's slack


def executor_version() -> str:
    try:
        from importlib.metadata import version
        return version("climate-platform")
    except Exception:
        return "unknown"


def is_alive(last_seen: Optional[datetime], now: Optional[datetime] = None, stale_after_s: int = STALE_AFTER_S) -> bool:
    """Pure staleness rule: alive iff a heartbeat exists and is no older than stale_after_s."""
    if last_seen is None:
        return False
    now = now or datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return (now - last_seen) <= timedelta(seconds=stale_after_s)


def summarize(rows: list[dict], now: Optional[datetime] = None, stale_after_s: int = STALE_AFTER_S) -> dict:
    """Pure: from heartbeat rows → {alive, last_seen, stale_after_s, workers}. Alive if ANY executor is fresh."""
    now = now or datetime.now(timezone.utc)
    workers = [{"worker": r["worker"], "queue": r["queue"], "hostname": r["hostname"], "version": r.get("version"),
                "last_seen": r["last_seen"], "alive": is_alive(r["last_seen"], now, stale_after_s)} for r in rows]
    last = max((r["last_seen"] for r in rows if r["last_seen"] is not None), default=None)
    return {"alive": any(w["alive"] for w in workers), "last_seen": last, "stale_after_s": stale_after_s, "workers": workers}


def write_heartbeat(worker: str, queue: str, hostname: Optional[str] = None) -> None:
    from core.db.session import get_session
    with get_session() as s:
        s.execute(text("""INSERT INTO worker_heartbeat (worker, queue, hostname, last_seen, version)
                          VALUES (:w, :q, :h, now(), :v)
                          ON CONFLICT (worker) DO UPDATE SET queue = EXCLUDED.queue, hostname = EXCLUDED.hostname,
                                                             last_seen = now(), version = EXCLUDED.version"""),
                  {"w": worker, "q": queue, "h": hostname or socket.gethostname(), "v": executor_version()})


def clear_heartbeat(worker: str) -> None:
    """Graceful stop: the row goes, so the executor is unavailable at once — not after the stale window."""
    from core.db.session import get_session
    with get_session() as s:
        s.execute(text("DELETE FROM worker_heartbeat WHERE worker = :w"), {"w": worker})


def read_heartbeats(session) -> list[dict]:
    rows = session.execute(text("SELECT worker, queue, hostname, last_seen, version FROM worker_heartbeat")).mappings().all()
    return [dict(r) for r in rows]


class Heartbeater:
    """Daemon thread that beats every `interval_s` until stopped; `stop()` clears the row."""

    def __init__(self, worker: str, queue: str, interval_s: int = HEARTBEAT_INTERVAL_S):
        self.worker, self.queue, self.interval_s = worker, queue, interval_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"heartbeat-{worker}", daemon=True)

    def start(self) -> "Heartbeater":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                write_heartbeat(self.worker, self.queue)
            except Exception as e:      # the DB being away must never kill the executor
                logger.warning("heartbeat for %s not written: %s", self.worker, e)
            self._stop.wait(self.interval_s)

    def stop(self) -> None:
        self._stop.set()
        try:
            clear_heartbeat(self.worker)
        except Exception as e:
            logger.warning("heartbeat row for %s not cleared: %s", self.worker, e)


# ── Celery wiring: the worker process owns exactly one Heartbeater ───────────────────────────────────────────
_worker_beat: Optional[Heartbeater] = None


def _queues_of(sender) -> str:
    try:
        return ",".join(sorted(q.name for q in sender.task_consumer.queues)) or "celery"
    except Exception:
        return "celery"


def on_worker_ready(sender=None, **_) -> None:
    global _worker_beat
    name = getattr(sender, "hostname", None) or f"celery@{socket.gethostname()}"
    _worker_beat = Heartbeater(name, _queues_of(sender)).start()
    logger.info("worker heartbeat started for %s every %ss", name, HEARTBEAT_INTERVAL_S)


def on_worker_shutdown(**_) -> None:
    global _worker_beat
    if _worker_beat:
        _worker_beat.stop()
        _worker_beat = None
