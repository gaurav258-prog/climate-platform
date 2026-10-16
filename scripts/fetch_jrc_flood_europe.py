"""Fetch the JRC's European river-flood maps and its map of European flood-protection standards — approved by the
product owner on 2026-10-16 (both downloads; about 2.85 GB and 957 KB):

  jrc_flood_europe             JRC / Copernicus EMS European river flood hazard maps (CEMS-EFAS flood_hazard v3.1.1),
                               LISFLOOD-FP, 3 arc-seconds (~90 m): depth at the 1-in-10, 20, 30, 40, 50, 75, 100, 200 and
                               500-year floods, plus the permanent-water-body and spurious-depth masks the README names
  jrc_flood_protection_europe  JRC PESETA IV: 'map of estimated flood defence standards in Europe … Cell values indicate
                               the estimated return period of design (in years) of local protection structures against
                               river floods' (PESETA IV collection description v3), 500 m GeoTIFF

Each folder's README, CHANGELOG and copyright notice are fetched with the data, so the licence and version the files
were taken under are held beside them. The plan is priced before anything is fetched (HEAD per file) and refused when
the bytes not yet held exceed --max-gb. Every file goes through scripts/download.py (retries, resumes); one that still
fails is recorded with the reason. The protection archive is unpacked into its own empty folder after its member names
are checked (no absolute paths, no '..'). Nothing here decides how the maps are used.

Usage: PYTHONPATH=. venv/bin/python -m scripts.fetch_jrc_flood_europe --max-gb 2.9 [--parallel 3] [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "datasets"
RETURN_PERIODS = (10, 20, 30, 40, 50, 75, 100, 200, 500)
DOCS = ("README.txt", "CHANGELOG.txt", "copyright.txt")
SOURCES = {
    "jrc_flood_europe": {
        "base": "https://jeodpp.jrc.ec.europa.eu/ftp/public/JRC-OpenData/CEMS-EFAS/flood_hazard",
        "dir": DEST / "jrc_flood_europe",
        "files": [f"Europe_RP{rp}_filled_depth.tif" for rp in RETURN_PERIODS]
                 + ["Europe_permanent_water_bodies.tif", "Europe_spurious_depth_areas.tif"] + list(DOCS),
        "source": "JRC / Copernicus EMS European river flood hazard maps (CEMS-EFAS flood_hazard), LISFLOOD-FP",
        "contents": "river flood depth (m) at return periods 10, 20, 30, 40, 50, 75, 100, 200, 500 years, 3 arc-seconds; "
                    "permanent water bodies and spurious-depth areas; README, CHANGELOG, copyright notice",
    },
    "jrc_flood_protection_europe": {
        "base": "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/PESETAIV/Paper_floods",
        "dir": DEST / "jrc_flood_protection_europe",
        "files": ["floodProtection_v2019_paper.zip", "PESETA_IV_collection_description-v3.pdf", "copyright.txt"],
        "source": "JRC PESETA IV floods collection — map of estimated flood defence standards in Europe "
                  "(Dottori et al. 2022)",
        "contents": "design return period (years) of local protection structures against river floods, 500 m GeoTIFF; "
                    "the collection description; copyright notice",
    },
}


def price(key: str, name: str) -> dict:
    src = SOURCES[key]
    from scripts.download import remote_size
    status, size = remote_size(f"{src['base']}/{name}")
    if status in (403, 404):
        return {"key": key, "file": name, "status": "absent"}
    if size is None:
        raise RuntimeError(f"{name}: the server answered {status} with no size")
    out = src["dir"] / name
    return {"key": key, "file": name, "bytes": size,
            "status": "held" if out.exists() and out.stat().st_size == size else "to_fetch"}


def plan_refusal(plan: list[dict], max_gb: float) -> str | None:
    need = sum(p["bytes"] for p in plan if p["status"] == "to_fetch")
    if need > max_gb * 1e9:
        return f"the plan needs {need / 1e9:.2f} GB not yet held, above the approved {max_gb:g} GB — refused"
    return None


def fetch(p: dict) -> dict:
    if p["status"] != "to_fetch":
        return p
    from scripts.download import download
    src = SOURCES[p["key"]]
    got = download(f"{src['base']}/{p['file']}", src["dir"] / p["file"], p["bytes"])
    return {**p, "status": "fetched" if got in ("fetched", "held") else "failed", "why": got}


def unpack_refusal(names: list[str]) -> str | None:
    """Why an archive's member names are not safe to unpack (absolute, or climbing out with '..'), or None."""
    for n in names:
        p = PurePosixPath(n)
        if p.is_absolute() or ".." in p.parts or n.startswith("\\") or ":" in p.parts[0]:
            return f"archive member '{n}' would land outside its folder — refused"
    return None


def unpack(archive: Path) -> list[str]:
    out = archive.with_suffix("")
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        why = unpack_refusal(names)
        if why:
            raise SystemExit(why)
        if out.exists() and any(out.iterdir()):
            return names
        out.mkdir(parents=True, exist_ok=True)
        z.extractall(out)
    return names


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-gb", type=float, required=True, help="the volume the product owner approved")
    ap.add_argument("--parallel", type=int, default=3)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    for src in SOURCES.values():
        src["dir"].mkdir(parents=True, exist_ok=True)
    jobs = [(k, n) for k, s in SOURCES.items() for n in s["files"]]
    with ThreadPoolExecutor(a.parallel) as ex:
        plan = list(ex.map(lambda j: price(*j), jobs))
    by: dict[str, int] = {}
    for p in plan:
        by[p["status"]] = by.get(p["status"], 0) + 1
    need = sum(p["bytes"] for p in plan if p["status"] == "to_fetch")
    print(f"{len(plan)} files: {by}; {need / 1e9:.3f} GB to fetch", flush=True)
    why = plan_refusal(plan, a.max_gb)
    if why:
        print(why)
        return 2
    if a.dry_run:
        return 0
    with ThreadPoolExecutor(a.parallel) as ex:
        results = list(ex.map(fetch, plan))
    from scripts.fetch_supply_datasets import record
    failed_any = False
    for key, src in SOURCES.items():
        mine = [r for r in results if r["key"] == key]
        failed = {r["file"]: r["why"] for r in mine if r["status"] == "failed"}
        failed_any = failed_any or bool(failed)
        files = [{"file": str((src["dir"] / r["file"]).relative_to(ROOT)), "bytes": (src["dir"] / r["file"]).stat().st_size,
                  "sha256": _sha(src["dir"] / r["file"])} for r in mine if r["status"] in ("fetched", "held")]
        unpacked = {}
        for f in files:
            if f["file"].endswith(".zip"):
                unpacked[f["file"]] = unpack(ROOT / f["file"])
        notice = src["dir"] / "copyright.txt"
        record(key, {"source": src["source"], "url": src["base"],
                     "approved": "product owner, 2026-10-16",
                     "contents": src["contents"],
                     "licence_notice_file": str(notice.relative_to(ROOT)) if notice.exists() else None,
                     "licence_status": "the folder's copyright notice is held beside the data; its terms are quoted "
                                       "into data/reference/hazard_intensity_layers.json before any use",
                     "absent": sorted(r["file"] for r in mine if r["status"] == "absent"), "failed": failed,
                     "files": files, "unpacked": unpacked})
    print({"fetched": sum(r["status"] == "fetched" for r in results), "held": sum(r["status"] == "held" for r in results),
           "absent": by.get("absent", 0), "failed": [r["file"] for r in results if r["status"] == "failed"]}, flush=True)
    return 1 if failed_any else 0


if __name__ == "__main__":
    raise SystemExit(main())
