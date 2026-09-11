"""Subsidence from OBSERVED ground motion — Copernicus EGMS InSAR (v2 of the subsidence channel, Europe).

The v1 channel reads a susceptibility class (Herrera et al. 2021). Tested against what the satellites measure, that
class does not rank where the ground sinks (rank correlation 0.10 outside glacial rebound, 2026-09-11). v2 scores the
measurement itself: the EGMS Ortho Level-3 vertical velocity (2020–2024, 100 m, GNSS-calibrated, EPSG:3035;
scripts/fetch_egms_tiles.py). Per H3 cell (res 8, ~0.7 km²):

    rate  = 90th percentile of (−velocity) over the cell's measured pixels (≥ MIN_PIXELS)   [mm/yr, sinking positive]
    score = piecewise-linear on the rate: 0 mm/yr → 0 · 2 → 25 · 5 → 50 · 10 → 75 · ≥ 20 → 100

The 90th percentile reads the sinking part of a cell (a building on soft fill next to stable ground), not its
average. The anchors are the EGMS legend range (±20 mm/yr is its "high" limit) split at rates that matter to a
structure over a decade (2 mm/yr ≈ 2 cm, 5 ≈ 5 cm, 10 ≈ 10 cm); disclosed, not fitted. Cells outside EGMS coverage
(non-EEA, or no measured points) are NOT scored by v2 — the v1 class remains there as a screening indicator.
Validation: scripts/../validators/subsidence_egms_holdout.py (rate from 2020–2021 epochs vs observed 2022–2024).
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

import numpy as np

TILE_DIR = "data/egms"
MIN_PIXELS = 20
PCT = 90
SUBSIDENCE_MODEL_VERSION = "subsidence-egms-observed-v2"
_ANCHORS = [(0.0, 0.0), (2.0, 25.0), (5.0, 50.0), (10.0, 75.0), (20.0, 100.0)]


def rate_to_score(rate_mm_yr: float) -> float:
    r = max(0.0, float(rate_mm_yr))
    for (r0, s0), (r1, s1) in zip(_ANCHORS, _ANCHORS[1:]):
        if r <= r1:
            return round(s0 + (s1 - s0) * (r - r0) / (r1 - r0), 2)
    return 100.0


@lru_cache(maxsize=1)
def _tile_index() -> dict:
    """tile name → path, plus each tile's EPSG:3035 bounds (E/N in the name are the lower-left corner in 100 km)."""
    out = {}
    if not os.path.isdir(TILE_DIR):
        return out
    for f in os.listdir(TILE_DIR):
        if f.startswith("EGMS_L3_E") and f.endswith("_U_2020_2024_1.tiff"):
            name = f.split("_")[2]                       # E35N28
            e, n = int(name[1:3]) * 100_000, int(name[4:6]) * 100_000
            out[name] = {"path": os.path.join(TILE_DIR, f), "bounds": (e, n, e + 100_000, n + 100_000)}
    return out


def _to_3035(lon: float, lat: float) -> tuple[float, float]:
    return _transformer().transform(lon, lat)


@lru_cache(maxsize=1)
def _transformer():
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)


def tile_for(lon: float, lat: float) -> Optional[str]:
    x, y = _to_3035(lon, lat)
    for name, t in _tile_index().items():
        left, b, r, tp = t["bounds"]
        if left <= x < r and b <= y < tp:
            return name
    return None


class TileReader:
    def __init__(self, name: str):
        import rasterio
        self.name = name
        self.ds = rasterio.open(_tile_index()[name]["path"])

    def close(self):
        self.ds.close()

    def cell_rate(self, h3_cell: str) -> Optional[dict]:
        """{rate, n_pixels, mean_velocity, min_velocity} for an H3 cell, or None with too few measured pixels."""
        import h3
        from rasterio.features import geometry_mask
        from rasterio.windows import from_bounds
        from shapely.geometry import Polygon
        poly = Polygon([_to_3035(lo, la) for la, lo in h3.cell_to_boundary(h3_cell)])
        minx, miny, maxx, maxy = poly.bounds
        win = from_bounds(minx, miny, maxx, maxy, self.ds.transform).round_offsets().round_lengths()
        if win.width < 1 or win.height < 1:
            return None
        arr = self.ds.read(1, window=win).astype("float32")
        if arr.size == 0:
            return None
        inside = ~geometry_mask([poly], out_shape=arr.shape, transform=self.ds.window_transform(win), invert=False)
        nod = self.ds.nodata
        valid = inside & np.isfinite(arr) & ((arr != nod) if nod is not None else True)
        if valid.sum() < MIN_PIXELS:
            return None
        v = arr[valid]
        rate = float(np.percentile(-v, PCT))
        return {"rate_mm_yr": round(rate, 2), "n_pixels": int(valid.sum()), "mean_velocity_mm_yr": round(float(v.mean()), 2),
                "min_velocity_mm_yr": round(float(v.min()), 2), "score": rate_to_score(rate)}


def score_subsidence_egms_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """On-demand v2 score for a point inside EGMS coverage; persists the row and retires the v1 class row for the cell.
    Outside coverage returns {'status': 'not_covered'} so the caller can fall back to the v1 class."""
    import uuid
    from datetime import datetime, timezone

    import h3
    from sqlalchemy import text

    from core.db.session import get_session
    from core.types import score_to_bucket
    cell = h3.latlng_to_cell(lat, lon, 8)
    name = tile_for(lon, lat)
    if name is None:
        return {"status": "not_covered", "h3_cell": cell}
    with get_session() as s:
        ex = s.execute(text("""SELECT CAST(risk_score AS FLOAT) rs, risk_bucket, model_version FROM canonical_scores
                               WHERE hazard_type='subsidence' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL"""),
                       {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
    if ex and ex["model_version"] == SUBSIDENCE_MODEL_VERSION:
        return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}
    r = TileReader(name)
    try:
        st = r.cell_rate(cell)
    finally:
        r.close()
    if st is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": f"fewer than {MIN_PIXELS} EGMS-measured pixels in this cell"}
    now = datetime.now(timezone.utc)
    with get_session() as s:
        s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='subsidence' AND h3_cell=:c AND scenario=:sc
                          AND time_horizon=:h AND valid_to IS NULL AND model_version <> :mv"""),
                  {"now": now, "c": cell, "sc": scenario, "h": horizon, "mv": SUBSIDENCE_MODEL_VERSION})
        s.execute(text("""INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score, risk_bucket,
                          model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
                          VALUES (:id,:c,8,'subsidence',:sc,:h,:score,:b,:mv,:now,CAST(:shap AS jsonb),:now,:now,NULL)
                          ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane) WHERE valid_to IS NULL DO NOTHING"""),
                  {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "score": st["score"], "b": score_to_bucket(st["score"]).value,
                   "mv": SUBSIDENCE_MODEL_VERSION, "now": now,
                   "shap": json.dumps({**st, "tile": name, "on_demand": True, "source": "Copernicus EGMS Ortho L3 vertical velocity 2020–2024 (100 m)",
                                       "method": f"{PCT}th percentile of observed subsidence rate over the cell's measured pixels → anchored 0–100 scale"})})
    return {"status": "scored", "h3_cell": cell, "risk_score": st["score"], "risk_bucket": score_to_bucket(st["score"]).value}
