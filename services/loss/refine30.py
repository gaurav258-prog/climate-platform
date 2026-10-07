"""The 30 m flood refinement and its pre-registered test (E171; data/reference/loss_protocol.json, terrain_refinement).

The JRC river-flood maps give a water depth per 90 m pixel. The refinement re-spreads that water over the Copernicus
GLO-30 surface (30 m), as the protocol states it before any run:

  water surface   in each wet 90 m pixel: the mean 30 m elevation of its land sub-pixels plus the mapped depth
  30 m depth      the surface minus each sub-pixel's elevation; wet above 0.05 m (the maps' own dry threshold)
  never spreads   water stays inside the pixels the JRC maps flood: the refinement can narrow a flood, not widen it

GLO-30 is a surface model (buildings and vegetation included), so a roof reads as dry ground: whether the refinement
helps is decided by the test, not assumed. The test judges both resolutions on the flood_jrc_ems validator's own nodes
against the share of each node inside the observed Copernicus EMS extent; the refinement is used only when it beats
the 90 m maps on both the pooled rank correlation and the pooled AUC. Every raster read goes through the isolated
sampler (services.geo.raster_sampler, E170)."""
from __future__ import annotations

import json
import math
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

from ml.scoring.flood_jrc import DEPTH_MIN_M, flood_score, tile_path, tiles_for_bounds, water_path
from services.loss import registry

GLO30 = registry.ROOT / "data" / "datasets" / "glo30"
LAYERS_FILE = registry.REF / "hazard_intensity_layers.json"
LAYER_KEY = "jrc_flood_30m"


@lru_cache(maxsize=512)
def _bounds(path: str) -> Optional[tuple]:
    from services.geo import raster_sampler
    got = raster_sampler.info(path)
    return tuple(got["bounds"]) if got else None


def dem_paths(minx: float, miny: float, maxx: float, maxy: float) -> Optional[list[Path]]:
    """The GLO-30 tiles a box overlaps, by their real bounds (a tile is shifted half a pixel off the whole degree);
    None when one of them is not on disk (a result is never partial)."""
    from scripts.fetch_glo30 import tile_name
    out = []
    for la in range(math.floor(miny) - 1, math.floor(maxy) + 1):
        for lo in range(math.floor(minx) - 1, math.floor(maxx) + 1):
            p = GLO30 / f"{tile_name(la, lo)}.tif"
            nominal = (lo, la, lo + 1, la + 1)
            if not (nominal[0] < maxx + 0.01 and nominal[2] > minx - 0.01 and nominal[1] < maxy + 0.01 and nominal[3] > miny - 0.01):
                continue                          # nowhere near the box
            if not p.exists():
                if la in range(math.floor(miny), math.floor(maxy) + 1) and lo in range(math.floor(minx), math.floor(maxx) + 1):
                    return None
                continue
            b = _bounds(str(p))
            if b and b[0] < maxx and b[2] > minx and b[1] < maxy and b[3] > miny:
                out.append(p)
    return out or None


def _centres(crop: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(x, y, value) of the pixels inside the crop's geometry that hold a value."""
    tr = crop["transform"]
    rows, cols = np.nonzero(crop["valid"])
    return tr.c + (cols + 0.5) * tr.a, tr.f + (rows + 0.5) * tr.e, crop["values"][rows, cols]


def respread_depths(parent: np.ndarray, z: np.ndarray, depth: np.ndarray) -> np.ndarray:
    """Each 30 m land sub-pixel's depth under the stated method — its 90 m pixel's water surface (the mean elevation of
    the sub-pixels plus the mapped depth) minus its own elevation; zero or below is dry. `parent` names each
    sub-pixel's 90 m pixel, `z` its elevation, `depth` its parent's mapped depth (wet parents only)."""
    if not parent.size:
        return np.zeros(0)
    _u, inv = np.unique(parent, return_inverse=True)
    n = np.bincount(inv)
    surface = np.bincount(inv, weights=z) / n + np.bincount(inv, weights=depth) / n
    return surface[inv] - z


def respread(parent: np.ndarray, z: np.ndarray, depth: np.ndarray) -> np.ndarray:
    """The 30 m depths that stand above the dry threshold (see respread_depths)."""
    d = respread_depths(parent, z, depth)
    return d[d > DEPTH_MIN_M]


def _pixels(b) -> Optional[dict]:
    """The box's 30 m land pixels, each tied to the 90 m pixel holding its centre: {x, y, key, z, depth (the parent's
    mapped depth; NaN where it holds none), wet (the parent is wet), land90, d90 (the wet 90 m depths)}. None when a
    raster is missing or the box has no land."""
    from shapely.geometry import mapping

    from services.geo import raster_sampler
    geom = mapping(b)
    dems = dem_paths(*b.bounds)
    if dems is None:
        return None
    parts = []                                    # one per JRC tile the box touches (they share one pixel grid)
    for name in tiles_for_bounds(*b.bounds):
        dp, wp = tile_path(name, 100), water_path(name)
        if not dp:
            return None
        d = raster_sampler.masked(dp, geom)
        w = raster_sampler.masked(wp, geom) if wp else None
        if d is None:
            continue                              # the box does not reach this tile
        land = d["inside"] & ~((w["values"] == 1) if w is not None else False)   # a dry pixel is nodata, still land
        depth = np.where(d["valid"] & land, d["values"].astype("float64"), np.nan)
        parts.append({"transform": d["transform"], "land": land, "depth": depth, "wet": land & (depth > DEPTH_MIN_M)})
    land90 = sum(int(p["land"].sum()) for p in parts)
    if not land90:
        return None
    wet90 = sum(int(p["wet"].sum()) for p in parts)
    d90 = np.concatenate([p["depth"][p["wet"]] for p in parts]) if wet90 else np.array([])
    xs, ys, keys, zs, depth, wet = [], [], [], [], [], []
    for path in dems:
        crop = raster_sampler.masked(str(path), geom)
        if crop is None:
            continue
        x, y, z = _centres(crop)
        for i, p in enumerate(parts):            # each 30 m sub-pixel into the 90 m pixel holding its centre
            tr, h, w_ = p["transform"], *p["land"].shape
            col = np.floor((x - tr.c) / tr.a).astype(int)
            row = np.floor((y - tr.f) / tr.e).astype(int)
            ok = (col >= 0) & (col < w_) & (row >= 0) & (row < h)
            ok[ok] = p["land"][row[ok], col[ok]]
            xs.append(x[ok]); ys.append(y[ok])
            keys.append(i * 10**8 + row[ok] * w_ + col[ok])
            zs.append(z[ok].astype("float64"))
            depth.append(p["depth"][row[ok], col[ok]])
            wet.append(p["wet"][row[ok], col[ok]])
    if not keys:
        return None
    out = dict(zip(("x", "y", "key", "z", "depth", "wet"), (np.concatenate(a) for a in (xs, ys, keys, zs, depth, wet))))
    if not out["key"].size:
        return None
    return {**out, "land90": land90, "d90": d90}


def box_stats(b) -> Optional[dict]:
    """{"m90": (wet share, mean wet depth), "m30": (wet share, mean wet depth)} at the 1-in-100-year period over a
    lon/lat polygon; None when a raster is missing or the box has no land."""
    px = _pixels(b)
    if px is None:
        return None
    w = px["wet"]
    w30 = respread(px["key"][w], px["z"][w], px["depth"][w])
    d90, land30 = px["d90"], int(px["key"].size)
    return {"m90": (d90.size / px["land90"], float(d90.mean()) if d90.size else 0.0),
            "m30": (w30.size / land30, float(w30.mean()) if w30.size else 0.0),
            "land": (px["land90"], land30)}


def box_pixel_counts(b, flooded, mapped) -> Optional[dict]:
    """Building scale (loss_protocol terrain_refinement.building_scale_test): over the box's 30 m land pixels whose
    centre lies in the area EMS mapped — hits, misses and false alarms of the 90 m and the 30 m map at the
    1-in-100-year period against the observed flooded extent."""
    import shapely
    px = _pixels(b)
    if px is None:
        return None
    seen = mapped.intersection(b)
    shapely.prepare(seen)
    inside = shapely.contains_xy(seen, px["x"], px["y"])
    if not inside.any():
        return None
    obs = np.zeros(inside.size, dtype=bool)
    wet_obs = flooded.intersection(b)
    if not wet_obs.is_empty:
        shapely.prepare(wet_obs)
        obs = shapely.contains_xy(wet_obs, px["x"], px["y"])
    w = px["wet"]
    d30 = np.zeros(inside.size)
    d30[w] = respread_depths(px["key"][w], px["z"][w], px["depth"][w])
    pred = {"m90": w, "m30": d30 > DEPTH_MIN_M}
    o = obs[inside]
    out = {"pixels": int(inside.sum()), "observed_wet": int(o.sum())}
    for k, pr in pred.items():
        p_ = pr[inside]
        out[k] = {"hits": int((p_ & o).sum()), "misses": int((~p_ & o).sum()), "false_alarms": int((p_ & ~o).sum())}
    return out


def _metrics(pred: list[float], obs: list[float]) -> dict:
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    y = np.asarray(obs) > 0.02
    return {"n": len(pred), "rho": round(float(spearmanr(pred, obs)[0]), 4),
            "auc_share_gt_2pct": round(float(roc_auc_score(y, pred)), 4) if 0 < y.sum() < len(y) else None}


def _paired_bootstrap(p90: list[float], p30: list[float], obs: list[float], n: int = 2000, seed: int = 7) -> dict:
    """How far the 30 m minus 90 m difference moves when the nodes are resampled (2,000 paired draws, fixed seed): the
    5th and 95th percentile of the difference in rank correlation and in AUC — reported with the verdict, so a
    difference inside sampling noise reads as such."""
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    a, b, o = np.asarray(p90), np.asarray(p30), np.asarray(obs)
    y = o > 0.02
    rng = np.random.default_rng(seed)
    d_rho, d_auc = [], []
    for _ in range(n):
        i = rng.integers(0, len(o), len(o))
        if 0 < y[i].sum() < len(i):
            d_rho.append(spearmanr(b[i], o[i])[0] - spearmanr(a[i], o[i])[0])
            d_auc.append(roc_auc_score(y[i], b[i]) - roc_auc_score(y[i], a[i]))
    q = lambda v: [round(float(np.nanpercentile(v, 5)), 4), round(float(np.nanpercentile(v, 95)), 4)]  # noqa: E731
    return {"rho": q(d_rho), "auc": q(d_auc), "draws": len(d_rho)}


def compare() -> dict:
    """Both resolutions on the validator's nodes, per event and pooled, and the protocol's verdict."""
    import pandas as pd

    from scripts.backtest_flood_ems import EVENTS, ems_extent, ems_mapped
    from services.validation.validators.flood_jrc import PANEL, event_nodes, observed_share
    rule = json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))["terrain_refinement"]
    data = pd.read_parquet(PANEL)
    p90, p30, obs, per_event, skipped = [], [], [], {}, 0
    for ev in EVENTS:
        ext, _fc = ems_extent(ev)
        mapped = ems_mapped(ev)
        m = data.event == ev["name"]
        if ext is None or ext.is_empty or mapped is None or not m.any():
            continue
        a, b_, o = [], [], []
        for _c, b in event_nodes(data.loc[m, "h3_cell"], ev, mapped):
            st = box_stats(b)
            if st is None:
                skipped += 1
                continue
            a.append(flood_score(*st["m90"])); b_.append(flood_score(*st["m30"]))
            o.append(observed_share(ext, mapped, b))
        if len(a) >= 10:
            per_event[ev["name"]] = {"m90": _metrics(a, o), "m30": _metrics(b_, o)}
        p90 += a; p30 += b_; obs += o
    m90, m30 = _metrics(p90, obs), _metrics(p30, obs)
    spread = _paired_bootstrap(p90, p30, obs)
    passed = (m30["rho"] > m90["rho"] and m30["auc_share_gt_2pct"] is not None and m90["auc_share_gt_2pct"] is not None
              and m30["auc_share_gt_2pct"] > m90["auc_share_gt_2pct"])
    return {"protocol": "terrain_refinement", "registered": rule["registered"], "run": date.today().isoformat(),
            "rule": rule["rule"], "pooled": {"m90": m90, "m30": m30}, "difference_90pct_interval": spread,
            "per_event": per_event,
            "nodes_without_both_rasters": skipped, "passed": bool(passed)}


def _scores(c: dict) -> dict:
    h, m, f = c["hits"], c["misses"], c["false_alarms"]
    return {"csi": round(h / (h + m + f), 4) if h + m + f else None, "hit_rate": round(h / (h + m), 4) if h + m else None,
            "false_alarm_ratio": round(f / (h + f), 4) if h + f else None, **c}


def _sum(rows: list[dict], k: str) -> dict:
    return {f: sum(r[k][f] for r in rows) for f in ("hits", "misses", "false_alarms")}


def building_scale(draws: int = 2000, seed: int = 7) -> dict:
    """The pre-registered building-scale test (loss_protocol.json, terrain_refinement.building_scale_test): the 90 m and
    the 30 m map, pixel by pixel at 30 m inside the area EMS mapped, on the flood_jrc_ems validator's judged nodes."""
    import pandas as pd

    from scripts.backtest_flood_ems import EVENTS, ems_extent, ems_mapped
    from services.validation.validators.flood_jrc import PANEL, event_nodes
    rule = json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))["terrain_refinement"]["building_scale_test"]
    data = pd.read_parquet(PANEL)
    rows, skipped = [], 0
    for ev in EVENTS:
        ext, _fc = ems_extent(ev)
        mapped = ems_mapped(ev)
        m = data.event == ev["name"]
        if ext is None or ext.is_empty or mapped is None or not m.any():
            continue
        for c, b in event_nodes(data.loc[m, "h3_cell"], ev, mapped):
            got = box_pixel_counts(b, ext, mapped)
            if got is None:
                skipped += 1
                continue
            rows.append({"event": ev["name"], "node": c, **got})
    per_event = {}
    for ev in dict.fromkeys(r["event"] for r in rows):
        rs = [r for r in rows if r["event"] == ev]
        per_event[ev] = {"nodes": len(rs), "pixels": sum(r["pixels"] for r in rs),
                         "m90": _scores(_sum(rs, "m90")), "m30": _scores(_sum(rs, "m30"))}
    pooled = {"nodes": len(rows), "pixels": sum(r["pixels"] for r in rows),
              "m90": _scores(_sum(rows, "m90")), "m30": _scores(_sum(rows, "m30"))}
    # paired block bootstrap: resample the nodes, a node's pixels moving together
    a = np.array([[r[k][f] for k in ("m90", "m30") for f in ("hits", "misses", "false_alarms")] for r in rows], dtype=float)
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(draws):
        t = a[rng.integers(0, len(a), len(a))].sum(axis=0)
        c90, c30 = t[0] / t[:3].sum(), t[3] / t[3:].sum()
        diffs.append(c30 - c90)
    lo, hi = float(np.percentile(diffs, 5)), float(np.percentile(diffs, 95))
    verdict = "better" if lo > 0 else "worse" if hi < 0 else "cannot tell"
    return {"protocol": "terrain_refinement.building_scale_test", "registered": rule["registered"],
            "run": date.today().isoformat(), "rule": rule["rule"], "pooled": pooled,
            "csi_difference_90pct_interval": [round(lo, 4), round(hi, 4)], "draws": draws,
            "verdict": verdict, "per_event": per_event, "nodes_without_both_rasters": skipped}


def record_building_scale(result: dict) -> None:
    """The building-scale result beside the node-scale one, in the layer's entry."""
    doc = json.loads(LAYERS_FILE.read_text(encoding="utf-8"))
    doc["layers"][LAYER_KEY]["building_scale_test"] = result
    LAYERS_FILE.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    registry.layers.cache_clear()


def record(result: dict) -> None:
    """Write the layer and its test into data/reference/hazard_intensity_layers.json. It stays a candidate: the registered
    rule says the refinement is used ONLY when it wins, so passing is necessary, and adopting it is a stated decision."""
    doc = json.loads(LAYERS_FILE.read_text(encoding="utf-8"))
    rule = json.loads((registry.REF / "loss_protocol.json").read_text(encoding="utf-8"))["terrain_refinement"]
    kept = {k: v for k, v in doc["layers"].get(LAYER_KEY, {}).items() if k == "building_scale_test"}
    doc["layers"][LAYER_KEY] = {**kept,
        "peril": "flood", "metric": "water_depth", "unit": "m", "version": "glo30-v1",
        "source": "the JRC river-flood maps (jrc_river_flood) re-spread over the Copernicus DEM GLO-30 Public surface",
        "refines": "jrc_river_flood", "terrain": "copernicus_glo30_test", "resolution_m": 30, "return_periods": [100],
        "method": rule["method"], "status": "candidate",
        "adoption": ("passed the registered rule; whether it replaces the 90 m maps is the product owner's decision — the "
                     f"90% interval of the difference (rank correlation {result['difference_90pct_interval']['rho']}, AUC "
                     f"{result['difference_90pct_interval']['auc']}) shows how much of the gain is sampling noise")
                    if result["passed"] else "not used: it did not beat the 90 m maps on both measures",
        "licence": None, "licence_status": "GLO-30: to verify before customer-facing use (data/reference/supply_datasets.json)",
        "test": result}
    LAYERS_FILE.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    registry.layers.cache_clear()
