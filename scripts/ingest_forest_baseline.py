"""Pre-stage Hansen Global Forest Change tiles for a plot book (optional, for offline/fast reads).

The determination engine (services/intelligence/forest.py) reads Hansen tiles over HTTP via
/vsicurl by default — no staging needed. This script downloads the `lossyear` tiles covering a
set of plots into data/forest/ so reads are local and offline: useful for a design-partner
deployment or when a whole book is scored at once. It writes a provenance manifest so every
staged tile is traceable to its exact source + version + retrieval date.

Usage:
    # stage the tiles covering every plot currently in the DB
    python scripts/ingest_forest_baseline.py --from-db
    # or explicit lon,lat points
    python scripts/ingest_forest_baseline.py --points " -1.6,6.7  -7.0,37.5 "
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

from services.intelligence.forest import GFC_BASE, GFC_VERSION, STAGE_DIR, tile_id

UA = {"User-Agent": "tellumen-forest-ingest/1.0"}


def _tiles_for_points(points: list[tuple[float, float]]) -> set[str]:
    return {tile_id(lat, lon) for lon, lat in points}


def _points_from_db() -> list[tuple[float, float]]:
    from core.db.session import get_session
    from sqlalchemy import text
    with get_session() as s:
        rows = s.execute(text("SELECT longitude, latitude FROM sc_sourcing_plots "
                              "WHERE longitude IS NOT NULL AND latitude IS NOT NULL")).fetchall()
    return [(float(lon), float(lat)) for lon, lat in rows]


def _download(tid: str, band: str = "lossyear") -> dict:
    fname = f"Hansen_{GFC_VERSION}_{band}_{tid}.tif"
    url = f"{GFC_BASE}/{fname}"
    out = os.path.join(STAGE_DIR, fname)
    if os.path.exists(out):
        return {"tile": tid, "file": out, "status": "cached", "bytes": os.path.getsize(out)}
    os.makedirs(STAGE_DIR, exist_ok=True)
    t0 = time.time()
    print(f"  downloading {fname} …", flush=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=1800) as r, open(out, "wb") as f:
        f.write(r.read())
    return {"tile": tid, "file": out, "status": "downloaded",
            "bytes": os.path.getsize(out), "seconds": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-db", action="store_true", help="stage tiles for every plot in the DB")
    ap.add_argument("--points", help="'lon,lat  lon,lat' whitespace-separated")
    args = ap.parse_args()

    points: list[tuple[float, float]] = []
    if args.from_db:
        points += _points_from_db()
    if args.points:
        for tok in args.points.split():
            lon, lat = tok.split(",")
            points.append((float(lon), float(lat)))
    if not points:
        print("no points — pass --from-db or --points"); return 2

    tiles = sorted(_tiles_for_points(points))
    print(f"{len(points)} plots → {len(tiles)} Hansen tile(s): {', '.join(tiles)}")
    manifest = {"dataset": GFC_VERSION, "base": GFC_BASE, "band": "lossyear",
                "cutoff_year": 2020, "retrieved": None, "tiles": []}
    for tid in tiles:
        manifest["tiles"].append(_download(tid))
    manifest_path = os.path.join(STAGE_DIR, "provenance.json")
    # `retrieved` is stamped by the caller's shell (date) — kept out of code (no Date.now here).
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    total_mb = sum(t.get("bytes", 0) for t in manifest["tiles"]) / 1e6
    print(f"staged {len(tiles)} tile(s), {total_mb:.0f} MB → {STAGE_DIR}  (provenance: {manifest_path})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
