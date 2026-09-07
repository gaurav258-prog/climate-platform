"""EFFIS burnt-area polygons for ALL of Europe, held-out years — the target for the wildfire hazard-climatology backtest.

Pulls every EFFIS MODIS burnt-area polygon (ms:modis.ba.poly) in the Europe box and keeps those with FIREDATE in
[FIRST_YEAR, LAST_YEAR] → data/wildfire_val/effis_europe_<first>_<last>.geojson. Big boxes make the WFS return 500,
so the box is split recursively into quadrants (same recipe as fetch_effis_burnt_area.py). These years are held
OUT of every input the climatology uses (burned-area history ends 2020, fire weather is a 1991-2020 climatology).
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_effis_europe.py [first_year last_year]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.fetch_effis_burnt_area import _wfs_bbox

EUROPE = (72.0, -25.0, 34.0, 45.0)      # N, W, S, E
OUT = Path("data/wildfire_val")


def main() -> int:
    y0, y1 = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (2022, 2024)
    n, w, s, e = EUROPE
    feats: dict = {}
    # 2°×2° tiles keep each request under the server's limit; the quadrant split handles the rest
    lat = s
    while lat < n:
        lon = w
        while lon < e:
            for f in _wfs_bbox(min(lat + 2, n), lon, lat, min(lon + 2, e)):
                fd = (f["properties"].get("FIREDATE") or "")[:4]
                if fd.isdigit() and y0 <= int(fd) <= y1:
                    feats[f["properties"]["id"]] = f
            lon += 2
        lat += 2
        print(f"  … lat {lat:.0f}: {len(feats)} polygons so far", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"effis_europe_{y0}_{y1}.geojson"
    ha = sum(float(f["properties"].get("AREA_HA") or 0) for f in feats.values())
    p.write_text(json.dumps({"type": "FeatureCollection", "years": [y0, y1], "n": len(feats), "burnt_ha": ha,
                             "source": "EFFIS burnt-area mapping (ms:modis.ba.poly), JRC / Copernicus EMS",
                             "features": list(feats.values())}))
    print(f"wrote {p}: {len(feats)} polygons, {ha:,.0f} ha")
    return 0


if __name__ == "__main__":
    sys.exit(main())
