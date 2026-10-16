"""Fetch Copernicus GLO-30 Public DEM tiles (E171/E172) for the 30 m flood refinement, from the public copernicus-dem-30m
bucket (no credentials), in the order the build order sets:

  test     the 1° tiles under the event box (flood_bbox, plus the half node the validator draws round each node) of every
           flood event with an observed Copernicus EMS extent in data/flood_val — exactly what the refinement's test
           against the 90 m maps reads
  assets   the tiles holding an asset location whose H3 cell floods in the JRC river-flood maps — refused until the
           refinement is in use (data/reference/hazard_intensity_layers.json, layer jrc_flood_30m: a passed test and
           status 'in_use'), so no download is spent on a layer that is not used

The GLO-30 is a surface model: its readme says it "represents the surface of the Earth including buildings,
infrastructure and vegetation". Its customer-facing use waits on the licence being read and recorded.

The plan is priced before anything is fetched: every tile's size is read from the server (HEAD) and the fetch refuses
when the tiles not yet held exceed --max-gb (the volume the user approved). Resumable: a tile whose size equals the
server's Content-Length is skipped; a tile the bucket does not hold (sea, or not released) is recorded as absent.
Usage: PYTHONPATH=. venv/bin/python -m scripts.fetch_glo30 --set test --max-gb 5 [--parallel 6] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BASE = "https://copernicus-dem-30m.s3.amazonaws.com"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "glo30"
LAYERS = ROOT / "data" / "reference" / "hazard_intensity_layers.json"
GRID_HALF = 0.05          # the validator's node box half-width (services/validation/validators/flood_jrc.py)


def tile_name(lat_floor: int, lon_floor: int) -> str:
    ns = f"{'N' if lat_floor >= 0 else 'S'}{abs(lat_floor):02d}_00"
    ew = f"{'E' if lon_floor >= 0 else 'W'}{abs(lon_floor):03d}_00"
    return f"Copernicus_DSM_COG_10_{ns}_{ew}_DEM"


def tiles_of_box(n: float, w: float, s: float, e: float) -> set[tuple[int, int]]:
    return {(la, lo) for la in range(math.floor(s), math.floor(n) + 1) for lo in range(math.floor(w), math.floor(e) + 1)}


def test_tiles() -> set[tuple[int, int]]:
    """The tiles under each EMS-observed event's box — the box the validator draws its nodes from, not the extent's
    own bounds (an extent can carry stray parts; E172)."""
    from scripts.build_multievent_flood import EVENTS
    from scripts.fetch_ems_flood_footprints import slug
    out = set()
    for ev in EVENTS:
        if (ROOT / "data" / "flood_val" / f"ems_{slug(ev['name'])}.geojson").exists():
            n, w, s, e = ev["flood_bbox"]
            out |= tiles_of_box(n + GRID_HALF, w - GRID_HALF, s - GRID_HALF, e + GRID_HALF)
    return out


def refinement_adopted() -> bool:
    """The refinement is in use: it passed its test AND was adopted (status 'in_use') — passing alone is not adoption."""
    layer = json.loads(LAYERS.read_text(encoding="utf-8"))["layers"].get("jrc_flood_30m") or {}
    return layer.get("status") == "in_use" and bool((layer.get("test") or {}).get("passed"))


def asset_tiles() -> set[tuple[int, int]]:
    from sqlalchemy import text

    from core.db.session import get_session
    with get_session() as s:
        return {(int(a), int(b)) for a, b in s.execute(text("""
            SELECT DISTINCT floor(latitude), floor(longitude) FROM hazard_intensity_samples
            WHERE layer_key = 'jrc_river_flood' AND cell_fraction > 0""")).all()}


def price(tile: tuple[int, int]) -> dict:
    name = tile_name(*tile)
    from scripts.download import remote_size
    status, size = remote_size(f"{BASE}/{name}/{name}.tif")
    if status in (403, 404):
        return {"tile": name, "status": "absent"}
    if size is None:
        raise RuntimeError(f"{name}: the server answered {status} with no size")
    out = OUT / f"{name}.tif"
    return {"tile": name, "bytes": size, "status": "held" if out.exists() and out.stat().st_size == size else "to_fetch"}


def plan_refusal(plan: list[dict], max_gb: float) -> str | None:
    need = sum(p["bytes"] for p in plan if p["status"] == "to_fetch")
    if need > max_gb * 1e9:
        return f"the plan needs {need / 1e9:.2f} GB not yet held, above the approved {max_gb:g} GB — refused"
    return None


def fetch(p: dict) -> dict:
    if p["status"] != "to_fetch":
        return p
    from scripts.download import download
    name = p["tile"]
    got = download(f"{BASE}/{name}/{name}.tif", OUT / f"{name}.tif", p["bytes"])
    return {**p, "status": "fetched" if got in ("fetched", "held") else "failed", "why": got}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=("test", "assets"), required=True)
    ap.add_argument("--max-gb", type=float, required=True, help="the volume the user approved for this fetch")
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.set == "assets" and not refinement_adopted():
        print("refused: the 30 m refinement is not in use (hazard_intensity_layers.json, jrc_flood_30m: a passed test and "
              "status 'in_use') — no asset tiles are fetched for a layer that is not used")
        return 2
    tiles = sorted(test_tiles() if a.set == "test" else asset_tiles())
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.parallel) as ex:
        plan = list(ex.map(price, tiles))
    by = {}
    for p in plan:
        by[p["status"]] = by.get(p["status"], 0) + 1
    need = sum(p["bytes"] for p in plan if p["status"] == "to_fetch")
    print(f"{len(tiles)} tiles for '{a.set}': {by}; {need / 1e9:.2f} GB to fetch", flush=True)
    why = plan_refusal(plan, a.max_gb)
    if why:
        print(why)
        return 2
    if a.dry_run:
        return 0
    with ThreadPoolExecutor(a.parallel) as ex:
        results = list(ex.map(fetch, plan))
    failed = {r["tile"]: r["why"] for r in results if r["status"] == "failed"}
    files = []
    for r in results:
        if r["status"] in ("fetched", "held"):
            p = OUT / f"{r['tile']}.tif"
            files.append({"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                          "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "set": a.set})
    from scripts.fetch_supply_datasets import record
    record(f"copernicus_glo30_{a.set}", {"source": "Copernicus DEM GLO-30 Public (copernicus-dem-30m, AWS Open Data)",
                                "url": BASE, "kind": "digital surface model (includes buildings and vegetation)",
                                "licence": None, "licence_status": "to verify before customer-facing use",
                                "licence_pointer": "the bucket readme: 'available on a free basis for the general public under the "
                                                   "terms and conditions of the Licence' at spacedata.copernicus.eu",
                                "absent": sorted(r["tile"] for r in results if r["status"] == "absent"),
                                "failed": failed,
                                "files": files})
    print({"fetched": sum(r["status"] == "fetched" for r in results), "held": sum(r["status"] == "held" for r in results),
           "failed": failed}, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
