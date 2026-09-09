"""Raster reads in their own process — a native crash inside GDAL can never take the API or a worker down.

Every point scorer that reads a GeoTIFF (landslide, subsidence, permafrost, soil erosion, soil degradation) goes
through this sampler. Reads run in ONE persistent child process per parent process (spawned, so it shares no
state); the parent waits with a timeout. If the child dies (a libtiff assertion, an out-of-memory kill) or the
read times out (a slow remote COG), the caller gets None — which every scorer already reports as
insufficient_data — and the child is respawned on the next call. Datasets stay open inside the child, so the
cost is one queue round-trip per read, not a reopen.

RASTER_SAMPLER_INPROCESS=1 runs reads in-process (unit tests, notebooks).
RASTER_SAMPLER_TIMEOUT_S sets the per-read timeout (default 20 s; remote COGs get RASTER_SAMPLER_REMOTE_TIMEOUT_S, 45 s).
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TIMEOUT_S = float(os.environ.get("RASTER_SAMPLER_TIMEOUT_S", "20"))
_REMOTE_TIMEOUT_S = float(os.environ.get("RASTER_SAMPLER_REMOTE_TIMEOUT_S", "45"))
_GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "GDAL_HTTP_MAX_RETRY": "2",
             "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES", "GDAL_HTTP_TIMEOUT": "30"}


# ── the child ───────────────────────────────────────────────────────────────────────────────────────────────
def _child_main(requests: mp.Queue, replies: mp.Queue) -> None:  # pragma: no cover — runs in the child
    for k, v in _GDAL_ENV.items():
        os.environ.setdefault(k, v)
    datasets: dict[str, Any] = {}
    while True:
        req = requests.get()
        if req is None:
            return
        rid, op, args = req
        try:
            replies.put((rid, True, _handle(datasets, op, args)))
        except Exception as e:
            replies.put((rid, False, f"{type(e).__name__}: {e}"))


def _open(datasets: dict, path: str):
    if path not in datasets:
        import rasterio
        datasets[path] = rasterio.open(path)
    return datasets[path]


def _handle(datasets: dict, op: str, args: dict):
    if op == "ping":
        return "pong"
    if op == "crash":            # test hook: a hard native-style death, no Python cleanup
        os._exit(134)
    src = _open(datasets, args["path"])
    if op == "info":
        b = src.bounds
        return {"bounds": [b.left, b.bottom, b.right, b.top], "crs": str(src.crs) if src.crs else None,
                "nodata": src.nodata, "count": src.count}
    if op == "sample":
        return [[float(v) for v in vals] for vals in src.sample(args["points"], indexes=args.get("band"))]
    if op == "window":
        from rasterio.windows import Window
        row, col = src.index(args["x"], args["y"])
        h = int(args.get("half", 4))
        a = src.read(int(args.get("band", 1)), window=Window(col - h, row - h, 2 * h + 1, 2 * h + 1))
        return a.tolist()
    raise ValueError(f"unknown op {op}")


# ── the parent ──────────────────────────────────────────────────────────────────────────────────────────────
class _Sampler:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Optional[mp.Process] = None
        self._req: Optional[mp.Queue] = None
        self._rep: Optional[mp.Queue] = None
        self._rid = 0
        self.deaths = 0          # observability: how often the child had to be replaced

    @staticmethod
    def _context():
        # forkserver: children fork from a clean server process that never re-imports the parent's __main__
        # (spawn does, which breaks under a stdin script or a frozen entry point) and never inherits the
        # parent's threads or GDAL state. Windows has no forkserver → spawn.
        try:
            return mp.get_context("forkserver")
        except ValueError:
            return mp.get_context("spawn")

    def _start(self) -> None:
        ctx = self._context()
        self._req, self._rep = ctx.Queue(), ctx.Queue()
        self._proc = ctx.Process(target=_child_main, args=(self._req, self._rep), name="raster-sampler", daemon=True)
        self._proc.start()

    def _kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill(); self._proc.join(timeout=2)
            except Exception:
                pass
        self._proc = self._req = self._rep = None

    def call(self, op: str, args: dict, timeout: Optional[float] = None) -> Optional[Any]:
        if os.environ.get("RASTER_SAMPLER_INPROCESS") == "1":
            try:
                return _handle(_INPROCESS_DATASETS, op, args)
            except Exception as e:
                logger.warning("raster read failed in-process (%s): %s", op, e)
                return None
        t = timeout or (_REMOTE_TIMEOUT_S if str(args.get("path", "")).startswith("/vsicurl") else _TIMEOUT_S)
        with self._lock:
            if self._proc is None or not self._proc.is_alive():
                if self._proc is not None:
                    self.deaths += 1
                    logger.warning("raster sampler child was dead — respawning (deaths so far: %d)", self.deaths)
                self._kill(); self._start()
            self._rid += 1
            rid = self._rid
            import queue
            import time
            deadline = time.monotonic() + t
            try:
                self._req.put((rid, op, args))
                while True:
                    try:
                        got_rid, ok, payload = self._rep.get(timeout=0.25)
                    except queue.Empty:
                        if not self._proc.is_alive():
                            raise RuntimeError(f"sampler child died (exit code {self._proc.exitcode})")
                        if time.monotonic() > deadline:
                            raise TimeoutError(f"no reply within {t:.0f}s")
                        continue
                    if got_rid != rid:
                        continue           # a stale reply from a timed-out earlier call
                    if not ok:
                        logger.warning("raster read failed (%s %s): %s", op, args.get("path"), payload)
                        return None
                    return payload
            except Exception as e:      # timeout or a dead child: replace the child, report nothing invented
                self.deaths += 1
                logger.warning("raster read on %s: %s — replacing the sampler child (deaths so far: %d)",
                               args.get("path"), e, self.deaths)
                self._kill()
                return None


_INPROCESS_DATASETS: dict[str, Any] = {}
_SAMPLER = _Sampler()


def info(path: str) -> Optional[dict]:
    """{bounds:[l,b,r,t], crs, nodata, count} or None (missing file, dead child, timeout)."""
    if not str(path).startswith("/vsicurl") and not os.path.exists(path):
        return None
    return _SAMPLER.call("info", {"path": str(path)})


def sample(path: str, points: list[tuple[float, float]], band: Optional[int] = None) -> Optional[list[list[float]]]:
    """Pixel values at (x, y) points in the raster's CRS; one list per point (one value per band)."""
    return _SAMPLER.call("sample", {"path": str(path), "points": [(float(x), float(y)) for x, y in points], "band": band})


def window(path: str, x: float, y: float, band: int = 1, half: int = 4):
    """A (2·half+1)² neighbourhood around (x, y) as a numpy array, or None."""
    got = _SAMPLER.call("window", {"path": str(path), "x": float(x), "y": float(y), "band": band, "half": half})
    if got is None:
        return None
    import numpy as np
    return np.asarray(got)


def crash_for_test() -> None:
    """Kill the child the hard way (os._exit) — proves the parent survives and respawns."""
    _SAMPLER.call("crash", {}, timeout=5)


def health() -> dict:
    p = _SAMPLER._proc
    return {"alive": bool(p and p.is_alive()), "pid": p.pid if p else None, "deaths": _SAMPLER.deaths,
            "inprocess": os.environ.get("RASTER_SAMPLER_INPROCESS") == "1"}
