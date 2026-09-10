"""River-flood hazard from the Copernicus EMS / JRC global flood hazard maps (v3 of the flood channel).

Source: CEMS-GLoFAS "Global river flood hazard maps" v2.1.2 — LISFLOOD hydrology + LISFLOOD-FP hydrodynamics,
3 arc-second (~90 m) inundation depth for seven return periods, global, 271 ten-degree tiles per period, plus the
permanent-water-body mask (scripts/fetch_jrc_flood_tiles.py lands RP10/RP100/RP500 + Permanent_WaterBodies under data/jrc_flood).

Cell statistic (H3 res 8, ~0.7 km²): the share of the cell inside the 1-in-100-year floodplain and the mean depth
over that share, plus the same at RP10 and RP500 for frequency context. Score:

    score = 100 × frac_RP100 × DDF(mean_depth_RP100)

where DDF is the JRC global depth–damage function for residential buildings, Europe (Huizinga, de Moel &
Szewczyk 2017, Table 3), a cited curve, not a fitted one: the score reads "share of the cell in the 100-year
floodplain, weighted by how damaging the water there is". Depths ≤ DEPTH_MIN_M are treated as dry (raster noise).
The maps are RIVER flooding only: pluvial/flash flooding and coastal surge are other channels (disclosed).
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import Optional

import numpy as np

TILE_DIR = "data/jrc_flood"
TILE_INDEX = "data/reference/jrc_flood_tiles.json"      # id → name, from the JRC tile_extents.geojson
RETURN_PERIODS = (10, 100, 500)
DEPTH_MIN_M = 0.05
FLOOD_MODEL_VERSION = "flood-jrc-glofas-rp-v3"

# Huizinga et al. (2017) residential Europe: damage fraction by depth (m). Linear between points, 1.0 beyond 6 m.
_DDF = [(0.0, 0.00), (0.5, 0.25), (1.0, 0.40), (1.5, 0.50), (2.0, 0.60), (3.0, 0.75), (4.0, 0.85), (5.0, 0.95), (6.0, 1.00)]


def damage_fraction(depth_m: float) -> float:
    if depth_m <= 0:
        return 0.0
    for (d0, f0), (d1, f1) in zip(_DDF, _DDF[1:]):
        if depth_m <= d1:
            return f0 + (f1 - f0) * (depth_m - d0) / (d1 - d0)
    return 1.0


def flood_score(frac_100: float, mean_depth_100: float) -> float:
    return round(100.0 * max(0.0, min(1.0, frac_100)) * damage_fraction(mean_depth_100), 2)


@lru_cache(maxsize=1)
def _tiles() -> dict:
    return {v: int(k) for k, v in json.load(open(TILE_INDEX)).items()}


def tile_name(lat: float, lon: float) -> Optional[str]:
    """Tile names are the top-left corner: N50_W100 spans 40–50 °N, 100–90 °W; the 0–10 °E column is named W0."""
    top = int(math.floor(lat / 10.0)) * 10 + 10
    left = int(math.floor(lon / 10.0)) * 10
    name = f"{'N' if top >= 0 else 'S'}{abs(top)}_{'E' if left > 0 else 'W'}{abs(left)}"
    return name if name in _tiles() else None


def tile_path(name: str, rp: int) -> Optional[str]:
    p = f"{TILE_DIR}/ID{_tiles()[name]}_{name}_RP{rp}_depth.tif"
    return p if os.path.exists(p) else None


def water_path(name: str) -> Optional[str]:
    p = f"{TILE_DIR}/ID{_tiles()[name]}_{name}_permanent_water.tif"
    return p if os.path.exists(p) else None


class TileReader:
    """Open rasters for one tile, reused across many cells (batch scoring runs in a script, not an API thread)."""

    def __init__(self, name: str):
        import rasterio
        self.name = name
        self.ds = {rp: rasterio.open(tile_path(name, rp)) for rp in RETURN_PERIODS if tile_path(name, rp)}
        wp = water_path(name)
        self.water = rasterio.open(wp) if wp else None

    def complete(self) -> bool:
        return len(self.ds) == len(RETURN_PERIODS)

    def close(self):
        for d in self.ds.values():
            d.close()
        if self.water:
            self.water.close()

    def polygon_stats(self, polygon) -> Optional[dict]:
        """{rp: (fraction_wet, mean_depth_wet, max_depth)} over the polygon (lon/lat).
        Encoding of the maps: dry land and sea are NODATA (−9999), a value is a flooded pixel's depth. Land pixels of
        the polygon are the denominator; permanent water bodies (river channels, lakes) are excluded from both the
        denominator and the numerator when the mask tile is on disk — a river channel is water, not flooded land."""
        from rasterio.features import geometry_mask
        from rasterio.windows import from_bounds
        out = {}
        minx, miny, maxx, maxy = polygon.bounds
        pw = None
        if self.water is not None:
            wwin = from_bounds(minx, miny, maxx, maxy, self.water.transform).round_offsets().round_lengths()
            if wwin.width >= 1 and wwin.height >= 1:
                pw = self.water.read(1, window=wwin) == 1        # 1 = permanent water, 255 = nodata (land)
        for rp, ds in self.ds.items():
            win = from_bounds(minx, miny, maxx, maxy, ds.transform).round_offsets().round_lengths()
            if win.width < 1 or win.height < 1:
                return None
            arr = ds.read(1, window=win).astype("float32")
            if arr.size == 0:                                # window clipped to nothing at a tile edge
                return None
            tr = ds.window_transform(win)
            inside = ~geometry_mask([polygon], out_shape=arr.shape, transform=tr, invert=False)
            if pw is not None and pw.shape == arr.shape:
                inside &= ~pw
            if inside.sum() == 0:
                return None
            nod = ds.nodata
            wet = inside & np.isfinite(arr) & (arr > DEPTH_MIN_M) & ((arr != nod) if nod is not None else True)
            out[rp] = (float(wet.sum() / inside.sum()), float(arr[wet].mean()) if wet.any() else 0.0,
                       float(arr[wet].max()) if wet.any() else 0.0)
        return out


def cell_polygon(h3_cell: str):
    import h3
    from shapely.geometry import Polygon
    return Polygon([(lo, la) for la, lo in h3.cell_to_boundary(h3_cell)])


def stats_to_row(st: dict) -> dict:
    f100, d100, m100 = st.get(100, (0.0, 0.0, 0.0))
    f10, d10, _ = st.get(10, (0.0, 0.0, 0.0))
    f500, d500, m500 = st.get(500, (0.0, 0.0, 0.0))
    return {"score": flood_score(f100, d100), "frac_rp100": round(f100, 4), "depth_rp100_m": round(d100, 2), "max_depth_rp100_m": round(m100, 2),
            "frac_rp10": round(f10, 4), "depth_rp10_m": round(d10, 2), "frac_rp500": round(f500, 4), "depth_rp500_m": round(d500, 2),
            "damage_fraction_rp100": round(damage_fraction(d100), 3)}


def score_flood_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """On-demand flood score for an arbitrary point (any-address lookup, uploads): reads the local JRC tiles for the
    point's H3 cell, persists the v3 row and retires an older-version row. Same contract as the other point scorers."""
    import uuid
    from datetime import datetime, timezone

    import h3
    from sqlalchemy import text

    from core.db.session import get_session
    from core.types import score_to_bucket
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""SELECT CAST(risk_score AS FLOAT) rs, risk_bucket, model_version FROM canonical_scores
                               WHERE hazard_type='flood' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
                                 AND COALESCE(score_lane,'standing')='standing'"""), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
    if ex and ex["model_version"] == FLOOD_MODEL_VERSION:
        return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}
    if scenario != "baseline" or horizon != "current":
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "flood projections are derived from the baseline by the projection job"}
    name = tile_name(lat, lon)
    if name is None or not tile_path(name, 100):
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no JRC river-flood tile on disk for this location"}
    r = TileReader(name)
    try:
        st = r.polygon_stats(cell_polygon(cell)) if r.complete() else None
    finally:
        r.close()
    if st is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no valid flood-map pixels in this cell (sea or nodata)"}
    row = stats_to_row(st); now = datetime.now(timezone.utc)
    with get_session() as s:
        s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='flood' AND h3_cell=:c AND scenario='baseline'
                          AND time_horizon='current' AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing' AND model_version <> :mv"""),
                  {"now": now, "c": cell, "mv": FLOOD_MODEL_VERSION})
        s.execute(text("""INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score, risk_bucket,
                          model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to, score_lane)
                          VALUES (:id,:c,8,'flood','baseline','current',:score,:b,:mv,:now,CAST(:shap AS jsonb),:now,:now,NULL,'standing')
                          ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane) WHERE valid_to IS NULL DO NOTHING"""),
                  {"id": str(uuid.uuid4()), "c": cell, "score": row["score"], "b": score_to_bucket(row["score"]).value, "mv": FLOOD_MODEL_VERSION, "now": now,
                   "shap": json.dumps({**row, "on_demand": True, "source": "JRC/CEMS global river flood hazard maps v2.1.2 (LISFLOOD-FP, 90 m)",
                                       "method": "share of the cell in the 1-in-100-year floodplain × Huizinga 2017 residential depth–damage fraction"})})
    return {"status": "scored", "h3_cell": cell, "risk_score": row["score"], "risk_bucket": score_to_bucket(row["score"]).value}
