"""Copernicus EGMS (European Ground Motion Service) — Ortho Level-3 vertical velocity tiles, the observed target for
the subsidence channel.

EGMS Ortho L3 = InSAR mean vertical ground velocity 2020–2024 on a 100 m grid (EPSG:3035), one GeoTIFF per 100 km
tile named EGMS_L3_E<xx>N<yy>_100km_U_2020_2024_1 (E/N = lower-left corner in 100 km units). Downloads are
token-gated (a personal token from the EGMS portal, `EGMS_TOKEN` in .env; never printed). There is no public tile
index, so the tiles are discovered by probing the grid over Europe's EPSG:3035 extent (HEAD requests), then pulled in
parallel; the GeoTIFF is kept, the zip discarded. Resumable. Lands data/egms/<tile>.tiff (git-ignored).

Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_egms_tiles.py [--parallel 6]
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

BASE = os.environ.get("EGMS_DOWNLOAD_BASE", "https://egms.land.copernicus.eu/insar-api/archive/download")
OUT = Path("data/egms")
E_RANGE, N_RANGE = range(9, 74), range(9, 56)          # EPSG:3035 100 km tiles spanning the EEA extent


def _token() -> str:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("EGMS_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("EGMS_TOKEN missing from .env")


def name(e: int, n: int) -> str:
    return f"EGMS_L3_E{e:02d}N{n:02d}_100km_U_2020_2024_1"


def exists(tile: str, tok: str) -> bool:
    try:                                                   # the archive does not answer HEAD; a 1-byte ranged GET does
        r = requests.get(f"{BASE}/{tile}.zip", params={"id": tok}, headers={"Range": "bytes=0-0"}, timeout=60, stream=True)
        ok = r.status_code in (200, 206)
        r.close()
        return ok
    except Exception:
        return False


def fetch(tile: str, tok: str) -> str:
    tif = OUT / f"{tile}.tiff"
    if tif.exists():
        return "have"
    import time
    r = None
    for attempt in range(8):
        try:
            r = requests.get(f"{BASE}/{tile}.zip", params={"id": tok}, timeout=(60, 600))
        except requests.RequestException:                   # timeout / reset: retry, never let one tile kill the run
            time.sleep(30 * (attempt + 1)); continue
        if r.status_code == 429:                            # throttled: back off and retry, never skip a tile silently
            time.sleep(30 * (attempt + 1)); continue
        break
    if r is None:
        return "unreachable"
    if r.status_code != 200:
        return f"http {r.status_code}"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        member = next(m for m in z.namelist() if m.lower().endswith((".tif", ".tiff")))
        tif.write_bytes(z.read(member))
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--parallel", type=int, default=2); a = ap.parse_args()
    tok = _token(); OUT.mkdir(parents=True, exist_ok=True)
    index = OUT / "_tiles.txt"
    if index.exists():
        tiles = index.read_text().split()
    else:
        cands = [name(e, n) for e in E_RANGE for n in N_RANGE]
        with ThreadPoolExecutor(16) as ex:
            tiles = [t for t, ok in zip(cands, ex.map(lambda t: exists(t, tok), cands)) if ok]
        index.write_text("\n".join(tiles) + "\n")
    print(f"{len(tiles)} EGMS vertical tiles exist", flush=True)
    done = {"ok": 0, "have": 0}
    with ThreadPoolExecutor(a.parallel) as ex:
        for i, st in enumerate(ex.map(lambda t: fetch(t, tok), tiles)):
            done[st] = done.get(st, 0) + 1
            if i % 25 == 0:
                print(f"  {i}/{len(tiles)} {done}", flush=True)
    print("done", done)
    return 0


if __name__ == "__main__":
    sys.exit(main())
