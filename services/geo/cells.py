"""The one place a map cell becomes a shape.

Every H3 cell drawn anywhere in the product — the supervisor's regional fallback (res-4), the agri sourcing grid,
the neighbourhood texture around a site and the asset hexagons (res-8) — comes through `cell_shape`, so no
hexagon ever spills into the sea or across a coastline. Land is the Eurostat GISCO world country layer
(2020, 1:3M), the same authority as the NUTS-3 regions; a cell is clipped to the union of every country it
touches, and named by the country holding most of its land. A cell that touches no land at all is reported as
`on_land=False`; the caller decides whether to draw it whole (an offshore site must still show) or drop it.
A cell is clipped only when the land layer is finer than the cell: a 1:3M coastline is accurate to about
1.5 km, so cells of resolution 5 and coarser (edge ≥ 8 km) are clipped, while finer cells (the 0.5 km site grid)
are drawn whole and flagged offshore only when the whole cell lies clearly beyond the coast. Clipping a 0.5 km cell
with a 1.5 km coastline would cut real land away — the wrong answer dressed as precision.
Satellite request footprints (Sentinel adapters) are observation bounds, not map shapes, and stay unclipped.
"""
from __future__ import annotations

import gzip
import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Optional

import h3

COUNTRIES_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "geo" / "countries_world_03m_2020.geojson.gz"
# GEOS prepared geometries are NOT thread-safe (their lazily built indexes race and segfault under concurrent use —
# seen twice in production-like runs of the API thread pool). Every predicate on the shared land index runs under
# this lock; a lookup costs well under a millisecond, so serialising them is free.
_GEOS_LOCK = threading.RLock()
LAYER_LABEL = "Eurostat GISCO countries 2020 · 1:3M"
LAYER_ACCURACY_KM = 1.5          # ground accuracy of a 1:3M line (≈0.5 mm on paper)
CLIP_EDGE_FACTOR = 4.0           # clip only when the cell edge is at least this many times the layer accuracy


def clips_at(resolution: int) -> bool:
    """True when the land layer is fine enough to clip cells of this resolution."""
    return h3.average_hexagon_edge_length(resolution, unit="km") >= CLIP_EDGE_FACTOR * LAYER_ACCURACY_KM


@lru_cache(maxsize=1)
def _land():
    """STRtree over land polygons. Countries are EXPLODED into their single polygons (a multipolygon such as France
    with its overseas territories has a world-spanning bounding box, which defeats the tree) and PREPARED, so a
    point or cell test costs microseconds, not tens of milliseconds. Each part keeps its country code."""
    import shapely
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    if not COUNTRIES_PATH.exists():
        return None
    with gzip.open(COUNTRIES_PATH, "rt") as f:
        feats = json.load(f)["features"]
    geoms, codes = [], []
    for x in feats:
        g = shape(x["geometry"]).buffer(0)
        for part in (g.geoms if g.geom_type == "MultiPolygon" else [g]):
            if part.is_empty:
                continue
            geoms.append(part); codes.append(x["properties"].get("CNTR_ID"))
    for g in geoms:
        shapely.prepare(g)
    return STRtree(geoms), geoms, codes


def _rings_lonlat(geom) -> list[list[list[float]]]:
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    return [[[round(x, 6), round(y, 6)] for x, y in p.exterior.coords] for p in polys if not p.is_empty and p.geom_type == "Polygon"]


@lru_cache(maxsize=65536)
def cell_shape(cell: str) -> dict:
    """→ {cell, resolution, clipped, on_land, country, geometry (GeoJSON, lon/lat), rings_lonlat, rings_latlon}.
    Coarse cells are clipped to land; fine cells are drawn whole and flagged offshore only when the whole cell
    lies further from the coast than the layer's accuracy."""
    from shapely.geometry import Polygon
    res = h3.get_resolution(cell)
    hexagon = Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(cell)])
    land = _land()
    with _GEOS_LOCK:
        return _shape_locked(cell, res, hexagon, land)


def _shape_locked(cell: str, res: int, hexagon, land) -> dict:
    from shapely.geometry import mapping
    from shapely.ops import unary_union
    geom, country, on_land, clipped = hexagon, None, True, False
    if land is not None:
        tree, geoms, codes = land
        tol_deg = LAYER_ACCURACY_KM / 111.0
        probe = hexagon.buffer(tol_deg)                      # what the coastline could plausibly reach
        hits = [int(i) for i in tree.query(probe) if geoms[int(i)].intersects(probe)]
        if not hits:
            on_land = False
        else:
            country = codes[max(hits, key=lambda i: probe.intersection(geoms[i]).area)]
            if clips_at(res):
                cut = hexagon.intersection(unary_union([geoms[i] for i in hits]))
                if cut.is_empty or cut.area <= 0:
                    on_land = False
                elif cut.area < hexagon.area * (1 - 1e-9):   # something was actually cut away
                    geom, clipped = cut, True
    rings = _rings_lonlat(geom)
    return {"cell": cell, "resolution": res, "clipped": clipped, "on_land": on_land, "country": country,
            "geometry": mapping(geom), "rings_lonlat": rings,
            "rings_latlon": [[[y, x] for x, y in ring] for ring in rings]}


def cell_shapes(cells: list[str]) -> dict[str, dict]:
    return {c: cell_shape(c) for c in cells}


def land_available() -> bool:
    return _land() is not None


def country_of(lat: float, lon: float) -> Optional[str]:
    """Country code under a point, from the same land layer (None at sea / without land data)."""
    land = _land()
    if land is None:
        return None
    from shapely.geometry import Point
    tree, geoms, codes = land
    pt = Point(lon, lat)
    with _GEOS_LOCK:
        for i in tree.query(pt):
            if geoms[int(i)].covers(pt):
                return codes[int(i)]
    return None
