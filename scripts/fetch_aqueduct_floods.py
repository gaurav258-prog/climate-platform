"""Fetch WRI Aqueduct Floods riverine inundation maps (projected flood depth by return period) — approved by the product
owner on 2026-10-07 (93 files, about 8.5 GB): the WATCH-forced present-day baseline and RCP4.5 / RCP8.5 for 2030, 2050
and 2080 from five climate models, at the 1-in-10, 1-in-100 and 1-in-500-year periods, from aqueduct.wridata.org.

File names follow the published convention `inunriver_{scenario}_{model}_{year}_{returnperiod}.tif` (nismod/aqueduct
data dictionary). Nothing here decides how the maps are used: their licence and how the future maps are built are read
from WRI's method note and recorded before any use (data/reference/hazard_intensity_layers.json).

The plan is priced before anything is fetched: every file's size is read from the server (HEAD) and the fetch refuses
when the files not yet held exceed --max-gb. A file the server does not hold is recorded as absent, never skipped
silently. Each file goes through scripts/download.py (retries, resumes a partial file); one that still fails is
recorded with the reason and the rest carry on. Resumable: a file whose size equals the server's Content-Length is kept.
Usage: PYTHONPATH=. venv/bin/python -m scripts.fetch_aqueduct_floods --max-gb 8.6 [--parallel 4] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

BASE = "https://aqueduct.wridata.org/AqueductFloods20"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "aqueduct_floods"
BASELINE = ("historical", "000000000WATCH", "1980")
MODELS = ("00000NorESM1-M", "0000GFDL-ESM2M", "0000HadGEM2-ES", "00IPSL-CM5A-LR", "MIROC-ESM-CHEM")
SCENARIOS = ("rcp4p5", "rcp8p5")
YEARS = ("2030", "2050", "2080")
RETURN_PERIODS = (10, 100, 500)


def names() -> list[str]:
    rps = [f"rp{rp:05d}" for rp in RETURN_PERIODS]
    out = [f"inunriver_{BASELINE[0]}_{BASELINE[1]}_{BASELINE[2]}_{rp}.tif" for rp in rps]
    out += [f"inunriver_{s}_{m}_{y}_{rp}.tif" for s in SCENARIOS for m in MODELS for y in YEARS for rp in rps]
    return out


def price(name: str) -> dict:
    h = requests.head(f"{BASE}/{name}", timeout=60)
    if h.status_code in (403, 404):
        return {"file": name, "status": "absent"}
    h.raise_for_status()
    size = int(h.headers["Content-Length"])
    out = OUT / name
    return {"file": name, "bytes": size, "status": "held" if out.exists() and out.stat().st_size == size else "to_fetch"}


def plan_refusal(plan: list[dict], max_gb: float) -> str | None:
    need = sum(p["bytes"] for p in plan if p["status"] == "to_fetch")
    if need > max_gb * 1e9:
        return f"the plan needs {need / 1e9:.2f} GB not yet held, above the approved {max_gb:g} GB — refused"
    return None


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
    record("aqueduct_floods_riverine", {
        "source": "WRI Aqueduct Floods hazard maps, riverine inundation (aqueduct.wridata.org/AqueductFloods20)",
        "url": BASE, "approved": "product owner, 2026-10-07 (93 files, about 8.5 GB)",
        "contents": "inundation depth by return period: WATCH-forced baseline (1980) and RCP4.5/RCP8.5 2030/2050/2080 from "
                    "five CMIP5 climate models; return periods 10, 100, 500 years",
        "licence": None, "licence_status": "to read from WRI's terms before any use",
        "method_status": "how the future maps are built: to read from WRI's method note before any use",
        "absent": sorted(r["file"] for r in results if r["status"] == "absent"), "failed": failed,
        "files": files})
    print({"fetched": sum(r["status"] == "fetched" for r in results), "held": sum(r["status"] == "held" for r in results),
           "absent": by.get("absent", 0), "failed": failed}, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
