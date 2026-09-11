"""SLF avalanche accidents — the observed, independent avalanche target for Switzerland.

Pulls "Avalanche accidents in Switzerland since 1970/71" (WSL Institute for Snow and Avalanche Research SLF,
EnviDat DOI 10.16904/envidat.411, WSL Data Policy / SLF Terms of Use): every known avalanche with at least one
person caught, with a WGS84 start-zone point. Lands the raw export (data/avalanche_val/slf_raw.csv), a cleaned
located-accident table (data/avalanche_val/slf_accidents.csv) and a provenance JSON. Resumable: an existing raw
file is reused unless --force. Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_slf_avalanches.py [--force]
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

from services.validation.validators.avalanche_slf import parse_slf_csv

DATASET = "avalanche-accidents-in-switzerland-since-1970-71"
API = f"https://www.envidat.ch/api/3/action/package_show?id={DATASET}"
OUT_DIR = Path("data/avalanche_val")
RAW = OUT_DIR / "slf_raw.csv"
CLEAN = OUT_DIR / "slf_accidents.csv"
PROV = OUT_DIR / "slf_provenance.json"


def _latest_resource(pkg: dict) -> dict:
    """The newest CSV resource (the dataset says 'consider the highest version number')."""
    res = [r for r in pkg["resources"] if (r.get("format") or "").upper() == "CSV"]
    if not res:
        raise RuntimeError("no CSV resource on the EnviDat package")
    return sorted(res, key=lambda r: r.get("name", ""))[-1]


def main(force: bool = False) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pkg = requests.get(API, timeout=60).json()["result"]
    res = _latest_resource(pkg)
    if RAW.exists() and not force:
        print(f"reusing {RAW} (pass --force to re-download)")
    else:
        r = requests.get(res["url"], timeout=120, allow_redirects=True)
        r.raise_for_status()
        RAW.write_bytes(r.content)
        print(f"downloaded {res['name']} → {RAW} ({len(r.content)} bytes)")
    raw_text = RAW.read_text(encoding="utf-8", errors="replace")
    rows = parse_slf_csv(raw_text)
    with CLEAN.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["avalanche_id", "date", "canton", "lat", "lon", "n_dead", "n_caught"])
        w.writeheader(); w.writerows(rows)
    banner = [ln.strip() for ln in raw_text.splitlines()[:3]]
    prov = {"dataset": DATASET, "title": pkg.get("title"), "doi": pkg.get("doi"), "licence": pkg.get("license_title"),
            "terms": "https://www.slf.ch/en/services-and-products/data-and-monitoring/slf-data-service.html",
            "resource": res.get("name"), "resource_url": res.get("url"), "banner": banner,
            "metadata_modified": pkg.get("metadata_modified"), "n_rows_located": len(rows),
            "fetched_at": datetime.now(timezone.utc).isoformat()}
    PROV.write_text(json.dumps(prov, indent=1))
    print(f"wrote {CLEAN}: {len(rows)} located accidents; provenance → {PROV}")
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv[1:]))
