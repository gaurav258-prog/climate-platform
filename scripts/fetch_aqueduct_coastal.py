"""Fetch WRI Aqueduct Floods coastal inundation maps (flood depth by return period) — approved by the product owner on
2026-10-23 (171 files, 8.07 GB): with subsidence, the present day and RCP4.5 / RCP8.5 for 2030, 2050 and 2080 at the
5th, 50th and 95th percentile of sea-level rise, at the nine return periods of the data dictionary (2 to 1,000 years).

File names follow WRI's data dictionary (_Aqueduct_Floods_Data_Dictionary.xlsx, read 2026-10-23):
`inuncoast_{scenario}_{subsidence}_{year}_{returnperiod}_{projection}.tif`, where the projection suffix '0' is the
'95th percentile (default)', '0_perc_05' the '5th percentile' and '0_perc_50' the '50th percentile'; 'wtsub' is
'Subsidence included'. The present day is `historical … hist`. The undocumented 'rp0001_5' maps are not fetched.

The plan is priced before anything is fetched (HEAD, scripts.fetch_aqueduct_floods.plan_refusal): the fetch refuses when
the files not yet held exceed --max-gb. Each file goes through scripts/download.py (retries, resumes); one that still
fails is recorded with the reason. The files land in their own folder (data/datasets/aqueduct_coastal, git-ignored) and
are read only from outside it, through the isolated raster reader. Each file's size and sha-256 are recorded in
data/reference/supply_datasets.json → aqueduct_floods_coastal.

Usage: venv/bin/python -m scripts.fetch_aqueduct_coastal --max-gb 8.1 [--parallel 4] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from scripts.fetch_aqueduct_floods import BASE, plan_refusal

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "aqueduct_coastal"
SUBSIDENCE = "wtsub"
SCENARIOS = ("rcp4p5", "rcp8p5")
YEARS = ("2030", "2050", "2080")
PROJECTIONS = ("0_perc_05", "0_perc_50", "0")          # sea-level rise: 5th, 50th, 95th percentile
RETURN_PERIODS = (2, 5, 10, 25, 50, 100, 250, 500, 1000)


def name(scenario: str, year: str, rp: int, projection: str) -> str:
    return f"inuncoast_{scenario}_{SUBSIDENCE}_{year}_rp{rp:04d}_{projection}.tif"


def names() -> list[str]:
    out = [name("historical", "hist", rp, "0") for rp in RETURN_PERIODS]
    out += [name(s, y, rp, p) for s in SCENARIOS for y in YEARS for p in PROJECTIONS for rp in RETURN_PERIODS]
    return out


def price(file: str) -> dict:
    from scripts.download import remote_size
    status, size = remote_size(f"{BASE}/{file}")
    if status in (403, 404):
        return {"file": file, "status": "absent"}
    if size is None:
        raise RuntimeError(f"{file}: the server answered {status} with no size")
    out = OUT / file
    return {"file": file, "bytes": size, "status": "held" if out.exists() and out.stat().st_size == size else "to_fetch"}


def fetch(p: dict) -> dict:
    if p["status"] != "to_fetch":
        return p
    from scripts.download import download
    got = download(f"{BASE}/{p['file']}", OUT / p["file"], p["bytes"])
    return {**p, "status": "fetched" if got in ("fetched", "held") else "failed", "why": got}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-gb", type=float, required=True, help="the volume the product owner approved")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(a.parallel) as ex:
        plan = list(ex.map(price, names()))
    by: dict[str, int] = {}
    for p in plan:
        by[p["status"]] = by.get(p["status"], 0) + 1
    need = sum(p["bytes"] for p in plan if p["status"] == "to_fetch")
    print(f"{len(plan)} files: {by}; {need / 1e9:.2f} GB to fetch", flush=True)
    why = plan_refusal(plan, a.max_gb)
    if why:
        print(why)
        return 2
    if a.dry_run:
        return 0
    with ThreadPoolExecutor(a.parallel) as ex:
        results = list(ex.map(fetch, plan))
    failed = {r["file"]: r["why"] for r in results if r["status"] == "failed"}
    files = []
    for r in results:
        if r["status"] in ("fetched", "held"):
            p = OUT / r["file"]
            files.append({"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
                          "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    from scripts.fetch_supply_datasets import record
    record("aqueduct_floods_coastal", {
        "source": "WRI Aqueduct Floods hazard maps, coastal inundation (aqueduct.wridata.org/AqueductFloods20)",
        "url": BASE, "approved": "product owner, 2026-10-23 (171 files, 8.07 GB)",
        "contents": "inundation depth by return period (2–1,000 years), subsidence included: the present day "
                    "(historical) and RCP4.5/RCP8.5 2030/2050/2080 at the 5th, 50th and 95th percentile of sea-level rise",
        "licence": "CC BY 4.0",
        "licence_status": "verified: WRI's catalogue record (datasets.wri.org API, package aqueduct-floods-hazard-maps) "
                          "states license_id 'cc-by' (2026-10-07, the riverine maps' record — one package)",
        "absent": sorted(r["file"] for r in results if r["status"] == "absent"), "failed": failed,
        "files": files})
    print({"fetched": sum(r["status"] == "fetched" for r in results), "held": sum(r["status"] == "held" for r in results),
           "absent": by.get("absent", 0), "failed": failed}, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
