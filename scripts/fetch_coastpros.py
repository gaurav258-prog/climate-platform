"""Fetch COASTPROS-EU, the coastal flood protection standards of Europe's coastal NUTS2 regions — approved by the product
owner on 2026-10-23 (Zenodo record 15024139, doi:10.5281/zenodo.15024139, CC BY 4.0; about 1.3 MB).

Every file the record lists is fetched and checked against the size and MD5 the record states; one that differs is
refused and removed. The files land in their own folder (data/datasets/coastpros_eu, git-ignored) and are read later
only from outside it (services.loss.protection reads the shapefile's regions). Each file's size, MD5 and sha-256 are
recorded in data/reference/supply_datasets.json → coastpros_eu.

Usage: venv/bin/python -m scripts.fetch_coastpros
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import requests

RECORD = "https://zenodo.org/api/records/15024139"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "coastpros_eu"


def main() -> int:
    rec = requests.get(RECORD, timeout=60).json()
    if rec["metadata"]["license"]["id"] != "cc-by-4.0":
        print(f"refused: the record's licence is {rec['metadata']['license']['id']}, not the approved CC BY 4.0")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    files = []
    for f in rec["files"]:
        out = OUT / f["key"]
        want_md5 = f["checksum"].removeprefix("md5:")
        if not (out.exists() and out.stat().st_size == f["size"]
                and hashlib.md5(out.read_bytes()).hexdigest() == want_md5):
            data = requests.get(f["links"]["self"], timeout=120).content
            if len(data) != f["size"] or hashlib.md5(data).hexdigest() != want_md5:
                print(f"refused: {f['key']} differs from the record's size or MD5")
                return 1
            out.write_bytes(data)
        raw = out.read_bytes()
        files.append({"file": str(out.relative_to(ROOT)), "bytes": len(raw), "md5": want_md5,
                      "sha256": hashlib.sha256(raw).hexdigest()})
        print(f"  {f['key']}: {len(raw)} bytes, MD5 as the record states")
    from scripts.fetch_supply_datasets import record
    record("coastpros_eu", {
        "source": "COASTPROS-EU: coastal flood protection standards per coastal NUTS2 region (Zenodo)",
        "url": "https://doi.org/10.5281/zenodo.15024139", "approved": "product owner, 2026-10-23 (about 1.3 MB)",
        "published": rec["metadata"]["publication_date"], "licence": "CC BY 4.0",
        "licence_status": "verified: the Zenodo record states license 'cc-by-4.0'", "files": files})
    print({"files": len(files)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
