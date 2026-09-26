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


# The published tiles are NOT on the nominal 10° grid: each is 11,999 px of 1/1200° (one pixel short of 10°) and its
# corner is shifted per tile — measured over all 271 tiles, left edge 0.0004–0.0296° west and top edge 0.0004–0.0121°
# north of the nominal corner. Neighbours still meet exactly (no gap, no overlap, one pixel grid), so a location is
# assigned by the tiles' REAL bounds, and a cell that straddles an edge is read from every tile it touches.
_MAX_TILE_OFFSET_DEG = 0.05


def nominal_tile_name(lat: float, lon: float) -> str:
    """The published name for the nominal 10° square: the top-left corner — N50_W100 spans 40–50 °N, 100–90 °W; the
    0–10 °E column is named W0. Only a naming rule — the tile's real extent is `tile_bounds`."""
    top = int(math.floor(lat / 10.0)) * 10 + 10
    left = int(math.floor(lon / 10.0)) * 10
    return f"{'N' if top >= 0 else 'S'}{abs(top)}_{'E' if left > 0 else 'W'}{abs(left)}"


@lru_cache(maxsize=None)
def tile_bounds(name: str) -> Optional[tuple[float, float, float, float]]:
    """(left, bottom, right, top) of a tile as published, read from its raster header; None if not on disk."""
    import rasterio
    p = next((tile_path(name, rp) for rp in RETURN_PERIODS if tile_path(name, rp)), None)
    if p is None:
        return None
    with rasterio.open(p) as ds:
        b = ds.bounds
    return (b.left, b.bottom, b.right, b.top)


def tiles_for_bounds(minx: float, miny: float, maxx: float, maxy: float) -> list[str]:
    """Every on-disk tile whose real extent overlaps the box (lon/lat)."""
    m = _MAX_TILE_OFFSET_DEG
    names = set()
    for la in range(int(math.floor((miny - m) / 10.0)), int(math.floor((maxy + m) / 10.0)) + 1):
        for lo in range(int(math.floor((minx - m) / 10.0)), int(math.floor((maxx + m) / 10.0)) + 1):
            n = nominal_tile_name(la * 10 + 5, lo * 10 + 5)
            if n in _tiles():
                names.add(n)
    out = []
    for n in sorted(names):
        b = tile_bounds(n)
        if b and b[0] < maxx and minx < b[2] and b[1] < maxy and miny < b[3]:
            out.append(n)
    return out


def tile_name(lat: float, lon: float) -> Optional[str]:
    """The on-disk tile whose real extent contains the point (None off every tile)."""
    for n in tiles_for_bounds(lon, lat, lon, lat):
        left, bottom, right, top = tile_bounds(n)
        if left <= lon < right and bottom < lat <= top:
            return n
    return None


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

    def polygon_counts(self, polygon) -> Optional[dict]:
        """{rp: (land_px, wet_px, depth_sum, depth_max)} for the part of the polygon (lon/lat) on THIS tile; None when the
        polygon does not reach it. Counts, not ratios, so a cell straddling tiles is summed exactly (`TileSet.stats`).
        Encoding of the maps: dry land and sea are NODATA (−9999), a value is a flooded pixel's depth. Permanent water
        bodies (river channels, lakes) are excluded from both the land count and the wet count — a river channel is
        water, not flooded land. The window is clipped to the tile BEFORE reading, so the mask and the pixels share one
        transform (a window past a tile edge is otherwise trimmed on read and the mask shifts off the data)."""
        from rasterio.errors import WindowError
        from rasterio.features import geometry_mask
        from rasterio.windows import Window, from_bounds
        ref = self.ds[100]
        try:
            win = (from_bounds(*polygon.bounds, ref.transform).round_offsets().round_lengths()
                   .intersection(Window(0, 0, ref.width, ref.height)))
        except WindowError:
            return None
        if win.width < 1 or win.height < 1:
            return None
        inside = ~geometry_mask([polygon], out_shape=(int(win.height), int(win.width)),
                                transform=ref.window_transform(win), invert=False)
        if self.water is not None:                            # same pixel grid as the depth rasters (all 271 tiles)
            inside &= ~(self.water.read(1, window=win) == 1)  # 1 = permanent water, 255 = nodata (land)
        land = int(inside.sum())
        out = {}
        for rp, ds in self.ds.items():
            arr = ds.read(1, window=win).astype("float32")
            nod = ds.nodata
            wet = inside & np.isfinite(arr) & (arr > DEPTH_MIN_M) & ((arr != nod) if nod is not None else True)
            out[rp] = (land, int(wet.sum()), float(arr[wet].sum(dtype="float64")), float(arr[wet].max()) if wet.any() else 0.0)
        return out


class TileSet:
    """Readers for every tile a polygon touches, opened on demand and kept for reuse (least-recently-used closed)."""

    def __init__(self, max_open: int = 8):
        from collections import OrderedDict
        self._open: "OrderedDict[str, TileReader]" = OrderedDict()
        self.max_open = max_open

    def _reader(self, name: str) -> TileReader:
        if name in self._open:
            self._open.move_to_end(name)
            return self._open[name]
        r = self._open[name] = TileReader(name)
        while len(self._open) > self.max_open:
            self._open.popitem(last=False)[1].close()
        return r

    def readable(self, polygon) -> bool:
        """Every tile the polygon touches is on disk with all return periods (so a result is never partial)."""
        names = tiles_for_bounds(*polygon.bounds)
        return bool(names) and all(self._reader(n).complete() for n in names)

    def stats(self, polygon) -> Optional[dict]:
        """{rp: (fraction_wet, mean_depth_wet, max_depth)} over the polygon, summed across every tile it touches.
        None when it has no land pixels (sea / permanent water) or is not fully readable (see `readable`)."""
        if not self.readable(polygon):
            return None
        tot = {rp: [0, 0, 0.0, 0.0] for rp in RETURN_PERIODS}
        for n in tiles_for_bounds(*polygon.bounds):
            c = self._reader(n).polygon_counts(polygon)
            for rp, (land, wet, dsum, dmax) in (c or {}).items():
                t = tot[rp]
                t[0] += land; t[1] += wet; t[2] += dsum; t[3] = max(t[3], dmax)
        if tot[100][0] == 0:
            return None
        return {rp: (wet / land, dsum / wet if wet else 0.0, dmax) for rp, (land, wet, dsum, dmax) in tot.items()}

    def close(self):
        for r in self._open.values():
            r.close()
        self._open.clear()


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
    poly = cell_polygon(cell)
    ts = TileSet()
    try:
        if not ts.readable(poly):
            return {"status": "insufficient_data", "h3_cell": cell, "reason": "no JRC river-flood tile on disk for this location"}
        st = ts.stats(poly)
    finally:
        ts.close()
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
