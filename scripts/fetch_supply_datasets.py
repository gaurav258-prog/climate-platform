"""Fetch the gridded inputs of the Supply outlook foundation (phase 2) — where and when each crop grows — verified
against the publisher's checksum, and record each in data/reference/supply_datasets.json (source, licence, version,
size, md5, sha-256), so the exact files the calibrations rest on are pinned. Files land under data/datasets/
(git-ignored); a file already present with the right checksum is not fetched again.

  mapspam_2020_harvested_area   IFPRI SPAM 2020 V2r2 — harvested area per crop, 5 arc-min GeoTIFF (CC BY 4.0;
                                "This data was provided by the International Food Policy Research Institute (IFPRI).
                                IFPRI bears no responsibility for the analyses or interpretations of the data
                                presented here.")
  cropgrids_v1_08               Tang et al. 2024 — harvested and crop area of 173 crops (FAOSTAT's list: olives,
                                grapes, almonds …), 2020, 0.05° NetCDF (CC BY 4.0)
  mirca_os_2015_crop_calendars  Kebede et al. 2025 — monthly crop calendars per sub-national unit, rainfed and irrigated,
                                incl. cocoa, coffee, oil palm (CC BY 4.0); 2015 tables
  ggcmi_phase3_crop_calendar    Jägermeyr et al. 2021 — planting and maturity day per 0.5° cell, rainfed and
                                irrigated, 18 annual crops (CC BY 4.0)

    python -m scripts.fetch_supply_datasets            # both
    python -m scripts.fetch_supply_datasets --only ggcmi_phase3_crop_calendar
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "datasets"
MANIFEST = ROOT / "data" / "reference" / "supply_datasets.json"
UA = {"User-Agent": "Tellumen dataset fetch (+https://tellumen.io)"}


def _dataverse_files(doi: str, match: str) -> list[dict]:
    d = requests.get("https://dataverse.harvard.edu/api/datasets/:persistentId/", params={"persistentId": doi},
                     headers=UA, timeout=60).json()["data"]["latestVersion"]
    return [{"name": f["dataFile"]["filename"], "size": f["dataFile"]["filesize"],
             "md5": (f["dataFile"].get("md5") or f["dataFile"]["checksum"]["value"]),
             "url": f"https://dataverse.harvard.edu/api/access/datafile/{f['dataFile']['id']}",
             "version": f"{d['versionNumber']}.{d.get('versionMinorNumber', 0)} ({d.get('releaseTime', '')[:10]})"}
            for f in d["files"] if match in f["dataFile"]["filename"]]


def _zenodo_files(record: str) -> list[dict]:
    d = requests.get(f"https://zenodo.org/api/records/{record}", headers=UA, timeout=60).json()
    return [{"name": f["key"], "size": f["size"], "md5": f["checksum"].split(":", 1)[1],
             "url": f["links"]["self"], "version": d.get("metadata", {}).get("version") or d.get("created", "")[:10]}
            for f in d["files"]]


def _figshare_files(article: str, match: str) -> list[dict]:
    d = requests.get(f"https://api.figshare.com/v2/articles/{article}", headers=UA, timeout=60).json()
    return [{"name": f["name"], "size": f["size"], "md5": f["computed_md5"], "url": f["download_url"],
             "version": f"v{d.get('version')} ({(d.get('modified_date') or '')[:10]})"}
            for f in d["files"] if match in f["name"]]


def _hydroshare_files(resource: str, names: tuple[str, ...]) -> list[dict]:
    d = requests.get(f"https://www.hydroshare.org/hsapi/resource/{resource}/files/", headers=UA, timeout=60).json()
    meta = requests.get(f"https://www.hydroshare.org/hsapi/resource/{resource}/sysmeta/", headers=UA, timeout=60).json()
    return [{"name": f["file_name"], "size": f["size"], "md5": f["checksum"], "url": f["url"],
             "version": f"updated {meta.get('date_last_updated', '')[:10]}"}
            for f in d["results"] if f["file_name"] in names]


DATASETS = {
    "mapspam_2020_harvested_area": {
        "files": lambda: _dataverse_files("doi:10.7910/DVN/SWPENT", "global_harvested_area.geotiff"),
        "source": "IFPRI, Global Spatially-Disaggregated Crop Production Statistics Data for 2020 (SPAM 2020), "
                  "Harvard Dataverse, doi:10.7910/DVN/SWPENT",
        "licence": "CC BY 4.0",
        "attribution": "This data was provided by the International Food Policy Research Institute (IFPRI). IFPRI bears "
                       "no responsibility for the analyses or interpretations of the data presented here.",
        # IFPRI requires its guestbook (name, e-mail …) and acceptance of its Terms of Use before each download: a person
        # downloads it at https://doi.org/10.7910/DVN/SWPENT and places it in data/datasets/<key>/ — this script then
        # verifies it against the publisher's checksum and records it; it never fills the guestbook itself
        "manual": "Download spam2020V2r2_global_harvested_area.geotiff.zip from https://doi.org/10.7910/DVN/SWPENT "
                  "(IFPRI guestbook + Terms of Use) into data/datasets/mapspam_2020_harvested_area/, then run again."},
    "cropgrids_v1_08": {
        "files": lambda: _figshare_files("22491997", "_NC_maps.zip") + _figshare_files("22491997", "CODES.zip"),
        "source": "Tang, F.H.M. et al. (2024), CROPGRIDS: a global geo-referenced dataset of 173 crops, Scientific "
                  "Data 11, 413; figshare doi:10.6084/m9.figshare.22491997 (v1.08)",
        "licence": "CC BY 4.0",
        "attribution": "CROPGRIDS (Tang et al. 2024), CC BY 4.0"},
    "mirca_os_2015_crop_calendars": {
        "files": lambda: _hydroshare_files("60a890eb841c460192c03bb590687145",
                                           ("MIRCA-OS_2015_rf.csv", "MIRCA-OS_2015_ir.csv", "README_crop_calendars.txt")),
        "source": "Kebede, E.A. et al. (2025), A global open-source dataset of monthly irrigated and rainfed cropped "
                  "areas (MIRCA-OS) for the 21st century, Scientific Data; HydroShare doi:10.4211/hs.60a890eb841c460192c03bb590687145",
        "licence": "CC BY 4.0",
        "attribution": "MIRCA-OS (Kebede et al. 2025), CC BY 4.0"},
    "ggcmi_phase3_crop_calendar": {
        "files": lambda: _zenodo_files("5062513"),
        "source": "Jägermeyr, J. et al. (2021), GGCMI Phase 3 crop calendar, Zenodo, doi:10.5281/zenodo.5062513 "
                  "(Nature Food 2, 873–885)",
        "licence": "CC BY 4.0",
        "attribution": "GGCMI Phase 3 crop calendar (Jägermeyr et al. 2021), CC BY 4.0"},
}


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(key: str) -> dict:
    spec = DATASETS[key]
    out_dir = DEST / key
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in spec["files"]():
        path = out_dir / f["name"]
        if not (path.exists() and path.stat().st_size == f["size"] and _md5(path) == f["md5"]):
            if spec.get("manual"):
                raise SystemExit(f"{key}: {spec['manual']}" + (" (the file present differs from the publisher's "
                                                                "checksum)" if path.exists() else ""))
            with requests.get(f["url"], headers=UA, timeout=900, stream=True) as r:
                r.raise_for_status()
                tmp = path.with_suffix(path.suffix + ".part")
                with tmp.open("wb") as w:
                    for chunk in r.iter_content(1 << 20):
                        w.write(chunk)
            if _md5(tmp) != f["md5"] or tmp.stat().st_size != f["size"]:
                tmp.unlink()
                raise SystemExit(f"{key}/{f['name']}: checksum or size differs from the publisher's — not kept")
            tmp.replace(path)
        rows.append({"file": f["name"], "bytes": f["size"], "md5": f["md5"], "sha256": _sha256(path), "url": f["url"]})
    return {"source": spec["source"], "licence": spec["licence"], "attribution": spec["attribution"],
            "version": spec["files"]()[0]["version"] if rows else None,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "path": str(out_dir.relative_to(ROOT)), "files": rows}


def record(key: str, entry: dict) -> None:
    """Write one dataset's entry into the manifest — re-read under an exclusive lock, so two fetchers running at once
    never overwrite each other's entries."""
    import fcntl
    with open(MANIFEST.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        manifest[key] = entry
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=list(DATASETS))
    a = ap.parse_args()
    for key in ([a.only] if a.only else list(DATASETS)):
        entry = fetch(key)
        record(key, entry)
        n = sum(r["bytes"] for r in entry["files"])
        print(f"{key}: {len(entry['files'])} file(s), {n / 1e6:.1f} MB, checksums verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
