"""Fetch Climate TRACE's asset-level sector packages that carry ownership — approved by the product owner on 2026-10-23
(power, manufacturing, fossil fuel operations and mineral extraction: 89.3 MB, CC BY 4.0).

Climate TRACE publishes, per sector, the emissions sources (one row per source, gas and period: coordinates, capacity,
emissions) and, for the subsectors whose owners are mapped, an ownership file: one row per owner along each source's
ownership chain with the owner's LEI ('parent_lei: GLEIF Legal Entity Identifier for parent entity', the package's
data guide) and its share of the source (overall_share_percent). The packages are read from downloads.climatetrace.org.

Every package's size is read first (HEAD) and the fetch refuses above --max-mb. Each goes through scripts/download.py.
Only the files named here are taken out of a zip — each subsector's sources and ownership files and the data guide —
never a path the archive chooses; everything lands in its own folder (data/datasets/climate_trace, git-ignored) and is
read later only from outside it. Each zip's and each extracted file's size and sha-256 are recorded in
data/reference/supply_datasets.json → climate_trace_assets.

Usage: venv/bin/python -m scripts.fetch_climate_trace --max-mb 90 [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

BASE = "https://downloads.climatetrace.org/latest/sector_packages/co2e_100yr"
PACKAGES = ("power", "manufacturing", "fossil_fuel_operations", "mineral_extraction")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "climate_trace"
# the members taken out of a package: a subsector's sources or ownership file, or the data guide
MEMBER = re.compile(r"^(DATA/[a-z0-9-]+_emissions_sources(_ownership)?_v\d+_\d+_\d+\.csv"
                    r"|ABOUT_THE_DATA/about_the_data_v\d+_\d+_\d+\.pdf)$")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def owned_subsectors(names: list[str]) -> set[str]:
    """The subsectors whose ownership file the package holds — only their sources are taken out."""
    return {m.group(1) for n in names if (m := re.match(r"^DATA/([a-z0-9-]+)_emissions_sources_ownership_", n))}


def wanted(names: list[str]) -> list[str]:
    owned = owned_subsectors(names)
    return [n for n in names if MEMBER.match(n) and (n.startswith("ABOUT_THE_DATA/")
                                                      or re.match(r"^DATA/([a-z0-9-]+)_", n).group(1) in owned)]


def extract(zpath: Path, dest: Path) -> list[dict]:
    out = []
    with zipfile.ZipFile(zpath) as z:
        for n in wanted(z.namelist()):
            target = dest / Path(n).name                    # flat: the archive's folders are never recreated
            with z.open(n) as src, target.open("wb") as dst:
                for chunk in iter(lambda: src.read(1 << 20), b""):
                    dst.write(chunk)
            out.append({"file": str(target.relative_to(ROOT)), "bytes": target.stat().st_size, "sha256": sha256(target),
                        "member": n})
    return out


def main() -> int:
    from scripts.download import download, remote_size
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-mb", type=float, required=True, help="the volume the product owner approved")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    plan = {}
    for p in PACKAGES:
        status, size = remote_size(f"{BASE}/{p}.zip")
        if size is None:
            print(f"{p}.zip: the server answered {status} with no size — refused")
            return 2
        plan[p] = size
    total = sum(plan.values())
    print(f"{len(plan)} packages, {total / 1e6:.1f} MB: {plan}", flush=True)
    if total > a.max_mb * 1e6:
        print(f"the plan needs {total / 1e6:.1f} MB, above the approved {a.max_mb:g} MB — refused")
        return 2
    if a.dry_run:
        return 0
    raw, data = OUT / "raw", OUT / "data"
    raw.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    zips, files, failed = [], [], {}
    for p, size in plan.items():
        zpath = raw / f"{p}.zip"
        got = download(f"{BASE}/{p}.zip", zpath, size)
        if got.startswith("failed"):
            failed[p] = got
            continue
        zips.append({"file": str(zpath.relative_to(ROOT)), "bytes": size, "sha256": sha256(zpath),
                     "url": f"{BASE}/{p}.zip"})
        files += extract(zpath, data)
        print(f"  {p}: {got}", flush=True)
    from scripts.fetch_supply_datasets import record
    record("climate_trace_assets", {
        "source": "Climate TRACE asset-level sector packages (CO2e 100-year), downloads.climatetrace.org/latest",
        "url": BASE, "approved": "product owner, 2026-10-23 (4 packages, 89.3 MB)",
        "contents": "emissions sources (coordinates, capacity, emissions) and ownership chains (owner, owner LEI, share "
                    "of the source) for the subsectors whose owners are mapped",
        "licence": "CC BY 4.0",
        "licence_status": "the data guide: 'All Climate TRACE data is freely available under the Creative Commons "
                          "Attribution 4.0 International Public License, unless otherwise noted below' "
                          "(ABOUT_THE_DATA/about_the_data_v5_10_0.pdf, held beside the data)",
        "packages": zips, "failed": failed, "files": files})
    print({"packages": len(zips), "files": len(files), "failed": failed}, flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
