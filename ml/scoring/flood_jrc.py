"""River-flood hazard from the Copernicus EMS / JRC global flood hazard maps (v3 of the flood channel).

Source: CEMS-GLoFAS "Global river flood hazard maps" v2.1.2 — LISFLOOD hydrology + LISFLOOD-FP hydrodynamics,
3 arc-second (~90 m) inundation depth for seven return periods, global, 271 ten-degree tiles per period, plus the
permanent-water-body mask (scripts/fetch_jrc_flood_tiles.py lands RP10/RP100/RP500 + Permanent_WaterBodies under data/jrc_flood).

Cell statistic (H3 res 8, ~0.7 km²): the share of the cell inside the 1-in-100-year floodplain and the mean depth
over that share, plus the same at RP10 and RP500 for frequency context. Score:

    score = 100 × frac_RP100 × DDF(mean_depth_RP100)

where DDF is the JRC global depth–damage function for residential buildings, Europe (Huizinga, de Moel &
Szewczyk 2017, EUR 28552 EN: the database workbook, sheet 'Damage functions', cells C4:C12 — the report itself shows the
European curves only as figures, Appendix F, Figure F-3; source files under data/datasets/sources/jrc105688_*), a cited
curve, not a fitted one: the score reads "share of the cell in the 100-year
floodplain, weighted by how damaging the water there is". Depths ≤ DEPTH_MIN_M are treated as dry (raster noise).
The maps are RIVER flooding only: pluvial/flash flooding and coastal surge are other channels (disclosed).
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from typing import Optional

TILE_DIR = "data/jrc_flood"
TILE_INDEX = "data/reference/jrc_flood_tiles.json"      # id → name, from the JRC tile_extents.geojson
RETURN_PERIODS = (10, 100, 500)
DEPTH_MIN_M = 0.05
FLOOD_MODEL_VERSION = "flood-jrc-glofas-rp-v3"
# Inside the countries the JRC European maps cover (CEMS-EFAS v3.1.1, the registered layer jrc_river_flood_europe), the
# score reads those maps — the product owner's decision of 2026-10-21, after they ranked all six EMS floods better
# (europe_maps_check) and the loss engine already read them there. Same statistic, same curve; its own model version.
EUROPE_LAYER = "jrc_river_flood_europe"
EUROPE_MODEL_VERSION = "flood-jrc-efas-rp-v4"
SOURCES = {FLOOD_MODEL_VERSION: "JRC/CEMS global river flood hazard maps v2.1.2 (LISFLOOD-FP, 90 m)",
           EUROPE_MODEL_VERSION: "JRC/CEMS European river flood hazard maps v3.1.1 (LISFLOOD-FP, 90 m)"}

# Huizinga et al. (2017) residential Europe: damage fraction by depth (m) — workbook 'Damage functions' C4:C12 (depths B4:B12).
# Linear between points, 1.0 beyond 6 m.
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
    from services.geo import raster_sampler
    p = next((tile_path(name, rp) for rp in RETURN_PERIODS if tile_path(name, rp)), None)
    if p is None:
        return None
    got = raster_sampler.info(p)
    return tuple(got["bounds"]) if got else None


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
    """One tile's rasters, read through the isolated raster sampler (services.geo.raster_sampler, E170): a native
    crash in GDAL can never take the API or a worker down. Holds paths only; the sampler's child keeps them open."""

    def __init__(self, name: str):
        self.name = name
        self.paths = {rp: tile_path(name, rp) for rp in RETURN_PERIODS if tile_path(name, rp)}
        self.water = water_path(name)

    def complete(self) -> bool:
        return len(self.paths) == len(RETURN_PERIODS)

    def close(self):
        pass

    def polygon_counts(self, polygon) -> Optional[dict]:
        """{rp: (land_px, wet_px, depth_sum, depth_max)} for the part of the polygon (lon/lat) on THIS tile; None when the
        polygon does not reach it (or a read failed). Counts, not ratios, so a cell straddling tiles is summed exactly
        (`TileSet.stats`). Encoding of the maps: dry land and sea are NODATA (−9999), a value is a flooded pixel's depth.
        Permanent water bodies (river channels, lakes) are excluded from both the land count and the wet count — a river
        channel is water, not flooded land."""
        from services.geo import raster_sampler
        ring = list(polygon.exterior.coords)
        exclude = {"path": self.water, "value": 1} if self.water else None   # 1 = permanent water, 255 = nodata (land)
        out = {}
        for rp, path in self.paths.items():
            z = raster_sampler.zonal(path, ring, above=DEPTH_MIN_M, exclude=exclude)
            if z is None:
                return None
            out[rp] = (z["inside"], z["present"], z["sum"], z["max"])
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


class EuropeMaps:
    """The European maps — one file per return period, on one grid — read through the isolated sampler, giving the same
    counts as TileSet: land pixels (permanent water excluded), wet pixels above DEPTH_MIN_M, their depth sum and maximum."""

    def __init__(self):
        from services.loss import registry
        L = registry.layer(EUROPE_LAYER)
        d = registry.ROOT / L["files"]["dir"]
        self.paths = {rp: str(d / L["files"]["pattern"].format(rp=rp)) for rp in RETURN_PERIODS}
        self.water = str(d / L["files"]["water"])

    def readable(self, polygon) -> bool:
        return all(os.path.exists(p) for p in (*self.paths.values(), self.water))

    def stats(self, polygon) -> Optional[dict]:
        """As TileSet.stats; None when the maps do not reach the polygon or it holds no land."""
        from services.geo import raster_sampler
        if not self.readable(polygon):
            return None
        ring, out = list(polygon.exterior.coords), {}
        for rp, path in self.paths.items():
            z = raster_sampler.zonal(path, ring, above=DEPTH_MIN_M, exclude={"path": self.water, "value": 1})
            if z is None or not z["inside"]:
                return None
            out[rp] = (z["present"] / z["inside"], z["sum"] / z["present"] if z["present"] else 0.0, z["max"])
        return out

    def close(self):
        pass


def cell_country(h3_cell: str) -> Optional[str]:
    """ISO alpha-2 of the country the platform's land layer places a cell in: its centre's; when the centre falls on no
    country (a coast, a wide river), the one country its corners fall in; else None."""
    import h3

    from services.geo.cells import country_of
    from services.reference.iso_country import to_iso2
    la, lo = h3.cell_to_latlng(h3_cell)
    c = to_iso2(country_of(la, lo))
    if c:
        return c
    corners = {to_iso2(country_of(a, b)) for a, b in h3.cell_to_boundary(h3_cell)} - {None}
    return corners.pop() if len(corners) == 1 else None


def europe_serves(country: Optional[str]) -> bool:
    """The European maps serve a place in a country they cover (ISO alpha-2), once the layer is in use."""
    from services.loss import registry
    if not country or registry.layer(EUROPE_LAYER).get("status") != "in_use":
        return False
    return country in registry.coverage_countries(EUROPE_LAYER)


def uses_europe(h3_cell: str) -> bool:
    return europe_serves(cell_country(h3_cell))


def read_polygon(polygon, country: Optional[str], tiles: Optional["TileSet"] = None, europe: Optional[EuropeMaps] = None):
    """(model version, statistics or None) for an outline in a country: the European maps in a covered country, the
    global maps elsewhere and wherever the European maps do not reach — as the loss engine reads the two."""
    if europe_serves(country):
        st = (europe or EuropeMaps()).stats(polygon)
        if st is not None:
            return EUROPE_MODEL_VERSION, st
    ts = tiles or TileSet()
    try:
        return FLOOD_MODEL_VERSION, (ts.stats(polygon) if ts.readable(polygon) else None)
    finally:
        if tiles is None:
            ts.close()


def point_country(lat: float, lon: float) -> Optional[str]:
    """ISO alpha-2 of the country the platform's land layer places a point in, or None."""
    from services.geo.cells import country_of
    from services.reference.iso_country import to_iso2
    return to_iso2(country_of(lat, lon))


def read_cell(h3_cell: str, tiles: Optional["TileSet"] = None, europe: Optional[EuropeMaps] = None):
    """read_polygon for one H3 cell, in the country cell_country places it."""
    return read_polygon(cell_polygon(h3_cell), cell_country(h3_cell), tiles=tiles, europe=europe)


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
    expected = EUROPE_MODEL_VERSION if uses_europe(cell) else FLOOD_MODEL_VERSION
    if ex and ex["model_version"] == expected:
        return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}
    if scenario != "baseline" or horizon != "current":
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "flood projections are derived from the baseline by the projection job"}
    version, st = read_cell(cell)
    if st is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no flood map on disk for this location, or no valid flood-map pixels in the cell (sea or nodata)"}
    row = stats_to_row(st); now = datetime.now(timezone.utc)
    with get_session() as s:
        s.execute(text("""UPDATE canonical_scores SET valid_to = :now WHERE hazard_type='flood' AND h3_cell=:c AND scenario='baseline'
                          AND time_horizon='current' AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing' AND model_version <> :mv"""),
                  {"now": now, "c": cell, "mv": version})
        s.execute(text("""INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score, risk_bucket,
                          model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to, score_lane)
                          VALUES (:id,:c,8,'flood','baseline','current',:score,:b,:mv,:now,CAST(:shap AS jsonb),:now,:now,NULL,'standing')
                          ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane) WHERE valid_to IS NULL DO NOTHING"""),
                  {"id": str(uuid.uuid4()), "c": cell, "score": row["score"], "b": score_to_bucket(row["score"]).value, "mv": version, "now": now,
                   "shap": json.dumps({**row, "on_demand": True, "source": SOURCES[version],
                                       "method": "share of the cell in the 1-in-100-year floodplain × Huizinga 2017 residential depth–damage fraction"})})
    return {"status": "scored", "h3_cell": cell, "risk_score": row["score"], "risk_bucket": score_to_bucket(row["score"]).value}
