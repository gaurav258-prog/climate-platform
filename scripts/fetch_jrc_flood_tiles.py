"""Fetch the JRC / Copernicus EMS global river flood hazard maps (v2.1.2) — the flood channel's foundation.

271 ten-degree tiles per return period, ~90 m depth GeoTIFFs (4–60 MB each). Pulls RP10, RP100 and RP500 into
data/jrc_flood (git-ignored) with N parallel downloads, resumable (existing complete files are skipped). Tile index
data/reference/jrc_flood_tiles.json is written from the service's tile_extents.geojson.
Dry land and sea are NODATA in the depth tiles; the permanent-water tiles mask river channels and lakes.
The README also lists a Spurious_Depth folder; it is not served at the documented URL (404, 2026-09-10).

Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_jrc_flood_tiles.py [--parallel 8] [--rps 10,100,500]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import requests

BASE = "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/CEMS-GLOFAS/flood_hazard"
OUT = Path("data/jrc_flood")
INDEX = Path("data/reference/jrc_flood_tiles.json")


def verify(urls: list[str], parallel: int) -> list[str]:
    """Compare every local file's size with the server's Content-Length; return the URLs that are missing or short.
    A tile is only trusted once it matches — a partially downloaded GeoTIFF opens but fails mid-read."""
    from concurrent.futures import ThreadPoolExecutor

    def check(u: str):
        f = OUT / u.rsplit("/", 1)[1]
        try:
            n = int(requests.head(u, timeout=60, allow_redirects=True).headers.get("content-length", -1))
        except Exception:
            return u
        return None if f.exists() and f.stat().st_size == n else u
    with ThreadPoolExecutor(parallel) as ex:
        bad = [u for u in ex.map(check, urls) if u]
    for u in bad:                                            # a short file must be re-fetched from zero, not resumed blindly
        f = OUT / u.rsplit("/", 1)[1]
        if f.exists():
            f.unlink()
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--parallel", type=int, default=8); ap.add_argument("--rps", default="10,100,500")
    ap.add_argument("--verify-only", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    g = requests.get(f"{BASE}/tile_extents.geojson", timeout=60).json()
    tiles = {str(f["properties"]["id"]): f["properties"]["name"] for f in g["features"]}
    INDEX.write_text(json.dumps(tiles, indent=0))
    urls = [f"{BASE}/RP{rp}/ID{i}_{n}_RP{rp}_depth.tif" for i, n in tiles.items() for rp in a.rps.split(",")]
    urls += [f"{BASE}/Permanent_WaterBodies/ID{i}_{n}_permanent_water.tif" for i, n in tiles.items()]
    print(f"{len(tiles)} tiles × {len(a.rps.split(','))} return periods + water masks = {len(urls)} files → {OUT}")
    for attempt in range(3):
        todo = verify(urls, a.parallel)
        print(f"  attempt {attempt + 1}: {len(todo)} files missing or incomplete", flush=True)
        if not todo or a.verify_only:
            break
        subprocess.run(["xargs", "-P", str(a.parallel), "-n", "1", "curl", "-s", "-O", "--retry", "3", "-m", "900"],
                       input="\n".join(todo) + "\n", text=True, cwd=OUT)
    bad = verify(urls, a.parallel)
    print("all files verified" if not bad else f"{len(bad)} files still incomplete")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
