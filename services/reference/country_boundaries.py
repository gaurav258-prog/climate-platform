"""
Country boundary clipping for the H3 hex-grid map.

The Earth is indexed in whole H3 cells, but a cell that straddles a coastline or a border
shouldn't be *drawn* spilling into the sea or the next country. Here we clip each display
hexagon to the land of the country it sits in (Natural Earth 1:50m admin-0 boundaries — an
authoritative public boundary set), so the grid reads as "cells within countries".

One-time load: parse the GeoJSON, build an STRtree over the country polygons. Per hex:
find the country under the cell's centre, intersect the hexagon with that country's land.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, Polygon, shape
from shapely.strtree import STRtree

_GEOJSON = Path(__file__).resolve().parents[2] / "data" / "reference" / "ne_50m_admin_0_countries.geojson"


@lru_cache(maxsize=1)
def _index() -> tuple[list, STRtree]:
    data = json.loads(_GEOJSON.read_text())
    geoms = [shape(f["geometry"]).buffer(0) for f in data["features"]]  # buffer(0) fixes any invalid rings
    return geoms, STRtree(geoms)


def _rings(geom) -> list[list[list[float]]]:
    """Flatten a (Multi)Polygon into a list of exterior rings as [[lon, lat], ...]."""
    out: list[list[list[float]]] = []
    polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon":
            continue
        out.append([[round(x, 5), round(y, 5)] for x, y in p.exterior.coords])
    return out


def clip_hex(boundary_lonlat: list[list[float]], center_lonlat: tuple[float, float]) -> list[list[list[float]]] | None:
    """Clip a hexagon (list of [lon, lat]) to the land of the country under its centre.

    Returns a list of rings (one hex can clip into several pieces at a jagged coast), or None
    when the cell's centre isn't on land — in which case the caller drops the cell entirely.
    """
    geoms, tree = _index()
    cx, cy = center_lonlat
    pt = Point(cx, cy)
    country = None
    for i in tree.query(pt):                     # STRtree returns candidate indices by bbox
        if geoms[int(i)].contains(pt):
            country = geoms[int(i)]
            break
    if country is None:
        return None                              # centre in the sea / no country → don't draw this cell
    try:
        clipped = Polygon(boundary_lonlat).buffer(0).intersection(country)
    except Exception:
        return [boundary_lonlat]                 # a clip failure shouldn't blank the grid — fall back to the raw hex
    if clipped.is_empty:
        return None
    rings = _rings(clipped)
    return rings or None
