"""Regional units for aggregation — what a supervisor is entitled to see without site-level access.

EU: NUTS-3 (Eurostat GISCO 2021, 1:20M) — the unit EBA Pillar 3 Template 5 and ESRS E1-9 use.
Elsewhere: an H3 resolution-4 hexagon (~1,770 km², comparable to a NUTS-3 region) — disclosed as such — clipped
to land by the one cell service (services/geo/cells.py — Eurostat GISCO countries 2020, 1:3M), which also names
its country. A hexagon that touches no land at all (an offshore site) is kept whole.
Point-in-polygon via a shapely STRtree over the 1,514 NUTS-3 polygons, built once per process.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

import h3

NUTS3_PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "geo" / "nuts3_eu_20m_2021.geojson"
H3_RES = 4


@lru_cache(maxsize=1)
def _index():
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    if not NUTS3_PATH.exists():
        return None
    feats = json.loads(NUTS3_PATH.read_text())["features"]
    geoms, meta = [], []
    for f in feats:
        p = f["properties"]
        geoms.append(shape(f["geometry"]))
        meta.append({"key": p["NUTS_ID"], "name": p["NUTS_NAME"], "country": p["CNTR_CODE"], "geometry": f["geometry"]})
    return STRtree(geoms), geoms, meta


def _hex_region(cell: str) -> dict:
    """The H3 cell as a GeoJSON region — clipped to land by the one cell service (services.geo.cells)."""
    from services.geo.cells import cell_shape
    c = cell_shape(cell)
    return {"key": cell, "name": f"hex {cell[:6]}…", "country": c["country"], "kind": "h3", "geometry": c["geometry"]}


def region_for(lat: float, lon: float) -> dict:
    """→ {key, name, country, kind: 'nuts3'|'h3', geometry (GeoJSON)}. Never None: outside NUTS → H3 hexagon."""
    idx = _index()
    if idx is not None:
        from shapely.geometry import Point
        tree, geoms, meta = idx
        pt = Point(lon, lat)
        for i in tree.query(pt):
            if geoms[int(i)].covers(pt):
                return {**meta[int(i)], "kind": "nuts3"}
    return _hex_region(h3.latlng_to_cell(lat, lon, H3_RES))


def aggregate_by_region(points: list[dict], entity_name: Optional[str] = None) -> list[dict]:
    """Roll located points up to regions: n_sites, value_eur, max/mean score, worst hazard, entities present."""
    out: dict[str, dict] = {}
    for p in points:
        r = region_for(p["lat"], p["lon"])
        g = out.setdefault(r["key"], {"key": r["key"], "name": r["name"], "country": r["country"], "kind": r["kind"],
                                      "geometry": r["geometry"], "n_sites": 0, "value_eur": 0.0, "max_score": None,
                                      "_sum": 0.0, "_n_scored": 0, "worst_hazard": None, "entities": set()})
        g["n_sites"] += 1
        g["value_eur"] += float(p.get("value_eur") or 0)
        if p.get("entity"):
            g["entities"].add(p["entity"])
        sc = p.get("score")
        if sc is not None:
            g["_sum"] += sc; g["_n_scored"] += 1
            if g["max_score"] is None or sc > g["max_score"]:
                g["max_score"], g["worst_hazard"] = sc, p.get("hazard")
    res = []
    for g in out.values():
        g["mean_score"] = round(g["_sum"] / g["_n_scored"], 1) if g["_n_scored"] else None
        g["entities"] = sorted(g["entities"])
        g["value_eur"] = round(g["value_eur"])
        del g["_sum"], g["_n_scored"]
        res.append(g)
    res.sort(key=lambda g: -(g["max_score"] or -1))
    return res
