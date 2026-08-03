"""Populate coastal_exposure — elevation + distance-to-coast per exposure cell (for SLR risk).

Elevation from the Open-Meteo elevation API (Copernicus GLO-90 DEM, no key). Distance-to-coast from
the Natural Earth 1:110m coastline (cached locally). Scoped to the cells that host exposure
(financial assets, own sites, sourcing plots) — the cells the coastal-flood hazard is scored for.

NOTE (disclosed): DEM elevation near buildings/vegetation can be biased high, and the 1:110m
coastline is coarse — both make this a SCREENING layer, honest about its resolution.

Run:  .venv/bin/python -m scripts.build_coastal_exposure
"""
from __future__ import annotations
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import h3
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from sqlalchemy import text

from core.db.session import get_session
from ml.scoring.sea_level import COAST_KM

ASSET_TABLES = ["portfolio_entities", "bank_assets", "realestate_properties",
                "sc_company_sites", "sc_sourcing_plots"]
COASTLINE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_coastline.geojson"
COASTLINE_CACHE = "data/coastline/ne_10m_coastline.geojson"   # fine coastline — resolves estuaries/deltas


def _coastline():
    os.makedirs(os.path.dirname(COASTLINE_CACHE), exist_ok=True)
    if not os.path.exists(COASTLINE_CACHE):
        print("fetching Natural Earth coastline…", flush=True)
        with urllib.request.urlopen(COASTLINE_URL, timeout=30) as r:
            open(COASTLINE_CACHE, "wb").write(r.read())
    gj = json.load(open(COASTLINE_CACHE))
    return unary_union([shape(f["geometry"]) for f in gj["features"]])


def _elevations(coords):
    """Open-Meteo elevation for [(lat,lon),...] (chunks of 100). Returns list aligned to coords."""
    out = []
    for i in range(0, len(coords), 100):
        chunk = coords[i:i + 100]
        q = urllib.parse.urlencode({
            "latitude": ",".join(f"{la:.5f}" for la, _ in chunk),
            "longitude": ",".join(f"{lo:.5f}" for _, lo in chunk)})
        url = f"https://api.open-meteo.com/v1/elevation?{q}"
        with urllib.request.urlopen(url, timeout=30) as r:
            out.extend(json.load(r).get("elevation", [None] * len(chunk)))
        time.sleep(0.3)
    return out


def main() -> int:
    now = datetime.now(timezone.utc)
    with get_session() as s:
        cells = set()
        for t in ASSET_TABLES:
            try:
                for c in s.execute(text(f"SELECT DISTINCT h3_cell FROM {t} WHERE h3_cell IS NOT NULL")).scalars():
                    cells.add(c)
            except Exception:
                pass
    cells = sorted(cells)
    coords = [h3.cell_to_latlng(c) for c in cells]
    print(f"{len(cells)} exposure cells; fetching elevation…", flush=True)
    elevs = _elevations(coords)

    print("computing distance to coast…", flush=True)
    from shapely.ops import nearest_points
    coast = _coastline()
    rows = []
    for cell, (la, lo), el in zip(cells, coords, elevs):
        near = nearest_points(coast, Point(lo, la))[0]   # true great-circle km, latitude-correct
        dist_km = h3.great_circle_distance((la, lo), (near.y, near.x), unit="km")
        rows.append({"h3": cell, "lat": la, "lon": lo, "el": (float(el) if el is not None else None),
                     "d": round(dist_km, 2), "coastal": dist_km <= COAST_KM,
                     "src": "Open-Meteo GLO-90 DEM + Natural Earth 110m coastline", "now": now})

    with get_session() as s:
        for r in rows:
            s.execute(text("""
                INSERT INTO coastal_exposure (h3_cell, latitude, longitude, elevation_m,
                    dist_to_coast_km, is_coastal, source, fetched_at)
                VALUES (:h3,:lat,:lon,:el,:d,:coastal,:src,:now)
                ON CONFLICT (h3_cell) DO UPDATE SET latitude=:lat, longitude=:lon, elevation_m=:el,
                    dist_to_coast_km=:d, is_coastal=:coastal, source=:src, fetched_at=:now
            """), r)

    n_coast = sum(1 for r in rows if r["coastal"])
    print(f"wrote {len(rows)} cells; {n_coast} within {COAST_KM:.0f} km of the coast")
    for r in sorted([r for r in rows if r["coastal"] and r["el"] is not None], key=lambda x: x["el"])[:6]:
        print(f"  coastal+low: {r['h3']}  elev={r['el']}m  dist={r['d']}km")
    return 0


if __name__ == "__main__":
    sys.exit(main())
