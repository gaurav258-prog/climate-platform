"""Copernicus Data Store retrievals made while the platform runs — the one door (E309).

The Climate and Atmosphere Data Stores (CDS, ADS) refuse a job when too many are queued for one dataset: 'Maximum
number queued requests for this dataset has been reached. Please configure your scripts to request data sequentially'.
Two address lookups were enough: each starts several hazard jobs on the worker's threads, and the drought, heat and
air-quality jobs reached the same datasets at once. So:

  retrieve(client, store, dataset, request, target)
      one request per store and dataset at a time on this machine — a file lock, so it holds across the worker's
      threads and across processes — and that refusal retried after a wait; still refused, or no turn within
      LOCK_WAIT_S, it raises CopernicusBusy, which a lookup records as 'busy' and shows in customer words
      (lookup.copernicus_busy), never as an unexpected error. Any other error is the caller's, unchanged.

Offline scripts (scripts/fetch_*, scripts/build_*) run one request after another and keep their own calls.
"""
from __future__ import annotations

import fcntl
import logging
import os
import re
import tempfile
import time
from contextlib import contextmanager
from typing import Callable

log = logging.getLogger(__name__)

BUSY_TEXT = "Maximum number queued requests"
WAITS_S = (30, 60, 120)          # between attempts after a refusal: about 3.5 minutes before giving up
LOCK_WAIT_S = 600                # the longest a job waits for its turn on one dataset
LOCK_DIR = os.path.join(tempfile.gettempdir(), "tellumen-copernicus")


class CopernicusBusy(RuntimeError):
    """The data store would not take the request now (its queue for the dataset was full, or no turn came)."""


def is_busy(exc: BaseException) -> bool:
    return BUSY_TEXT in str(exc)


@contextmanager
def _turn(store: str, dataset: str, wait_s: float, sleep: Callable[[float], None]):
    os.makedirs(LOCK_DIR, exist_ok=True)
    path = os.path.join(LOCK_DIR, re.sub(r"[^A-Za-z0-9._-]", "_", f"{store}-{dataset}") + ".lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + wait_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise CopernicusBusy(f"no turn on {store} {dataset} within {wait_s:.0f}s") from None
                sleep(0.5)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def retrieve(client, store: str, dataset: str, request: dict, target: str, *, waits: tuple = WAITS_S,
             lock_wait_s: float = LOCK_WAIT_S, sleep: Callable[[float], None] = time.sleep) -> None:
    """client.retrieve(dataset, request, target), one at a time per store and dataset, a refusal retried after each
    of `waits`; CopernicusBusy when it is still refused."""
    with _turn(store, dataset, lock_wait_s, sleep):
        for attempt in range(len(waits) + 1):
            try:
                client.retrieve(dataset, request, target)
                return
            except Exception as e:
                if not is_busy(e):
                    raise
                if attempt == len(waits):
                    raise CopernicusBusy(f"{store} {dataset}: refused after {attempt + 1} attempts") from e
                log.warning("copernicus %s %s busy — retrying in %ss (attempt %d)", store, dataset, waits[attempt],
                            attempt + 1)
                sleep(waits[attempt])


def mark_lookup_busy(lookup_id: str, now) -> None:
    """A lookup the data store would not take ends 'busy' — shown to the user as lookup.copernicus_busy, a reason to try
    again in a few minutes, not as a failed score."""
    from sqlalchemy import text

    from core.db.session import get_session
    log.warning("lookup %s: the Copernicus data store is busy", lookup_id)
    with get_session() as s:
        s.execute(text("UPDATE public_lookups SET status='busy', completed_at=:now WHERE lookup_id=:id"),
                  {"now": now, "id": lookup_id})
