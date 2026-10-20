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


def _open(datasets: dict, path: str, env: Optional[dict] = None):
    if path not in datasets:
        import rasterio
        with rasterio.Env(**(env or {})):
            datasets[path] = rasterio.open(path)
    return datasets[path]


def _handle(datasets: dict, op: str, args: dict):
    if op == "ping":
        return "pong"
    if op == "crash":            # test hook: a hard native-style death, no Python cleanup
        os._exit(134)
    src = _open(datasets, args["path"], args.get("env"))
    if op == "info":
        b = src.bounds
        return {"bounds": [b.left, b.bottom, b.right, b.top], "crs": str(src.crs) if src.crs else None,
                "nodata": src.nodata, "count": src.count, "width": src.width, "height": src.height,
                "transform": list(src.transform)[:6]}
    if op == "sample":
        return [[float(v) for v in vals] for vals in src.sample(args["points"], indexes=args.get("band"))]
    if op == "window":
        from rasterio.windows import Window
        row, col = src.index(args["x"], args["y"])
        h = int(args.get("half", 4))
        a = src.read(int(args.get("band", 1)), window=Window(col - h, row - h, 2 * h + 1, 2 * h + 1))
        return a.tolist()
    if op == "zonal":
        return _zonal(datasets, src, args)
    if op == "zone_bins":
        return _zone_bins(datasets, src, args)
    if op == "masked":
        import numpy as np
        import rasterio
        from rasterio.features import geometry_mask
        from rasterio.mask import mask as rio_mask
        with rasterio.Env(**(args.get("env") or {})):
            arr, tr = rio_mask(src, [args["geometry"]], crop=True, filled=False)
        a = arr[0]
        # inside: the geometry alone (pixel centres); valid: inside AND holding a value — a nodata pixel is still
        # inside the shape (E172: a dry pixel of the flood maps is nodata, and is land, not outside)
        inside = ~geometry_mask([args["geometry"]], out_shape=a.shape, transform=tr, invert=False)
        return {"values": np.ma.getdata(a).tolist(), "inside": inside.tolist(),
                "valid": (inside & ~np.ma.getmaskarray(a)).tolist(), "transform": [tr.a, tr.b, tr.c, tr.d, tr.e, tr.f]}
    raise ValueError(f"unknown op {op}")


def _zonal(datasets: dict, src, args: dict):
    """Counts over the pixels whose centres fall in a polygon (in the raster's CRS): how many are inside (less any
    pixel the exclude mask flags), how many of those hold a valid value above the threshold, and the sum and maximum of
    those values. None when the polygon does not reach the raster. The window is clipped to the raster before reading,
    so the mask and the pixels share one transform."""
    import numpy as np
    from rasterio.errors import WindowError
    from rasterio.features import geometry_mask
    from rasterio.windows import Window, from_bounds
    from shapely.geometry import Polygon
    poly = Polygon(args["polygon"])
    try:
        win = (from_bounds(*poly.bounds, src.transform).round_offsets().round_lengths()
               .intersection(Window(0, 0, src.width, src.height)))
    except WindowError:
        return None
    if win.width < 1 or win.height < 1:
        return None
    inside = ~geometry_mask([poly], out_shape=(int(win.height), int(win.width)), transform=src.window_transform(win),
                            invert=False)
    ex = args.get("exclude")
    if ex:
        inside &= ~(_open(datasets, ex["path"]).read(1, window=win) == ex["value"])
    a = src.read(int(args.get("band", 1)), window=win).astype("float32")
    nod = src.nodata
    present = inside & np.isfinite(a) & ((a != nod) if nod is not None else True)
    if args.get("above") is not None:
        present &= a > float(args["above"])
    out = {"inside": int(inside.sum()), "present": int(present.sum()),
           "sum": float(a[present].sum(dtype="float64")), "max": float(a[present].max()) if present.any() else 0.0}
    if args.get("values"):
        out["values"] = a[present].tolist()
    return out


def _zone_bins(datasets: dict, src, args: dict):
    """Per-shape statistics over one window of rasters on the zone raster's grid. A shape's zone is the pixels whose
    centres fall in it (one shape per pixel: the last drawn) where the zone raster holds a value above `above`, less any
    pixel the exclude mask flags. For each raster of `stack`: how many zone pixels hold a value above `above` in each
    interval between consecutive `edges` (the last open above), and the sum of those values — the rest are dry. With
    `lookup` (a raster on any grid and CRS): how many zone pixel centres fall on each of its values, and how many fall
    off it. {shape id: {zone, counts, sums, lookup, off}}; empty when no shape has a zone pixel in the window."""
    import numpy as np
    from pyproj import Transformer
    from rasterio.features import rasterize
    from rasterio.windows import Window
    edges = np.asarray(args["edges"], dtype="float64")
    above = float(args["above"])
    if edges[0] > above:
        raise ValueError("the first edge must not lie above the dry threshold")
    win = Window(*args["window"]).intersection(Window(0, 0, src.width, src.height))
    tr = src.window_transform(win)
    ids = rasterize([(g, int(i)) for g, i in args["shapes"]], out_shape=(int(win.height), int(win.width)),
                    transform=tr, fill=0, dtype="int32")

    def wet(ds):
        a = ds.read(1, window=win)
        ok = np.isfinite(a) & (a > above)
        return a, (ok & (a != ds.nodata)) if ds.nodata is not None else ok

    _a, zone = wet(src)
    zone &= ids > 0
    ex = args.get("exclude")
    if ex:
        zone &= ~(_open(datasets, ex["path"]).read(1, window=win) == ex["value"])
    if not zone.any():
        return {}
    rows, cols = np.nonzero(zone)
    uniq, idx = np.unique(ids[rows, cols], return_inverse=True)
    nb, ns = len(edges), len(uniq)
    counts, sums = [], []
    for path in args["stack"]:
        a, ok = wet(_open(datasets, path))
        v, w = a[rows, cols].astype("float64"), ok[rows, cols]
        key = idx[w] * nb + (np.searchsorted(edges, v[w], side="right") - 1)
        counts.append(np.bincount(key, minlength=ns * nb).reshape(ns, nb))
        sums.append(np.bincount(key, weights=v[w], minlength=ns * nb).reshape(ns, nb))
    out = {int(u): {"zone": int((idx == k).sum()), "counts": [c[k].tolist() for c in counts],
                    "sums": [s[k].tolist() for s in sums], "lookup": [], "off": 0} for k, u in enumerate(uniq)}
    lk = args.get("lookup")
    if lk:
        ls = _open(datasets, lk["path"])
        cc, rr = cols + 0.5, rows + 0.5                                         # pixel centres
        x, y = Transformer.from_crs(src.crs, ls.crs, always_xy=True).transform(
            tr.a * cc + tr.b * rr + tr.c, tr.d * cc + tr.e * rr + tr.f)
        x, y, inv = np.asarray(x), np.asarray(y), ~ls.transform
        fc, fr = inv.a * x + inv.b * y + inv.c, inv.d * x + inv.e * y + inv.f
        lr, lc = np.floor(fr).astype("int64"), np.floor(fc).astype("int64")
        on = (lr >= 0) & (lr < ls.height) & (lc >= 0) & (lc < ls.width)
        if on.any():
            r0, c0 = int(lr[on].min()), int(lc[on].min())
            block = ls.read(1, window=Window(c0, r0, int(lc[on].max()) - c0 + 1, int(lr[on].max()) - r0 + 1))
            vals = block[lr[on] - r0, lc[on] - c0].astype("float64")
            pair = np.stack([idx[on].astype("float64"), vals], axis=1)
            got, n = np.unique(pair, axis=0, return_counts=True)
            for (k, v), c in zip(got, n):
                out[int(uniq[int(k)])]["lookup"].append([float(v), int(c)])
        for k in np.unique(idx[~on]):
            out[int(uniq[k])]["off"] = int((idx[~on] == k).sum())
    return out


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


def zonal(path: str, polygon: list[tuple[float, float]], above: Optional[float] = None,
          exclude: Optional[dict] = None, band: int = 1, values: bool = False) -> Optional[dict]:
    """{inside, present, sum, max[, values]} over the pixels of `path` whose centres fall in `polygon` (raster CRS);
    `exclude` = {path, value} masks pixels of a raster on the same grid; `above` counts only values above it;
    `values` returns the present pixels' values too. None when the polygon misses the raster, the file is absent, or
    the read failed."""
    if not str(path).startswith("/vsicurl") and not os.path.exists(path):
        return None
    return _SAMPLER.call("zonal", {"path": str(path), "polygon": [(float(x), float(y)) for x, y in polygon],
                                   "above": above, "exclude": exclude, "band": band, "values": values})


def zone_bins(path: str, window: tuple[int, int, int, int], shapes: list[tuple[dict, int]], stack: list[str],
              edges: list[float], above: float, exclude: Optional[dict] = None, lookup: Optional[str] = None,
              timeout: float = 900.0) -> Optional[dict]:
    """Per-shape zone statistics over one window (col, row, width, height) of `path`'s grid — see _zone_bins. `shapes`
    are (GeoJSON geometry in the raster's CRS, id > 0); every raster of `stack` and `exclude` shares the grid; `lookup`
    is a raster on any grid. None when the file is absent or the read failed — never a partial answer."""
    if not os.path.exists(path):
        return None
    return _SAMPLER.call("zone_bins", {"path": str(path), "window": [int(v) for v in window], "shapes": shapes,
                                       "stack": [str(p) for p in stack], "edges": [float(e) for e in edges],
                                       "above": float(above), "exclude": exclude,
                                       "lookup": {"path": str(lookup)} if lookup else None}, timeout=timeout)


def masked(path: str, geometry: dict, env: Optional[dict] = None) -> Optional[dict]:
    """The raster cropped to a GeoJSON geometry (raster CRS): {values, inside, valid, transform} — `inside` marks the
    pixels whose centres fall in the geometry (the rest of the bounding box is not the geometry); `valid` those of them
    that hold a value (not the raster's nodata). None on a failed read."""
    got = _SAMPLER.call("masked", {"path": str(path), "geometry": geometry, "env": env})
    if got is None:
        return None
    import numpy as np
    from affine import Affine
    return {"values": np.asarray(got["values"]), "inside": np.asarray(got["inside"], dtype=bool),
            "valid": np.asarray(got["valid"], dtype=bool), "transform": Affine(*got["transform"])}


def crash_for_test() -> None:
    """Kill the child the hard way (os._exit) — proves the parent survives and respawns."""
    _SAMPLER.call("crash", {}, timeout=5)


def health() -> dict:
    p = _SAMPLER._proc
    return {"alive": bool(p and p.is_alive()), "pid": p.pid if p else None, "deaths": _SAMPLER.deaths,
            "inprocess": os.environ.get("RASTER_SAMPLER_INPROCESS") == "1"}
