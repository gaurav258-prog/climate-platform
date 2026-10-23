"""Read, for every issuer with an LEI, its GLEIF record and the entities GLEIF records it consolidates — approved by the
product owner on 2026-10-23 (GLEIF API reads, CC0) — to match the parent company a register of facilities names (the
EEA's industrial register names it only by its name) to an issuer.

  /lei-records/{lei}                       the issuer's legal name, other names, legal form and country
  /lei-records/{lei}/ultimate-children     the entities whose ultimate accounting-consolidating parent it is
  /lei-records/{lei}/direct-children       the entities it consolidates directly

Licence: 'The data available through the Access Service are provided under the CC0 licence' (GLEIF, LEI data terms of
use, read 2026-10-23). Every response is kept as read (data/datasets/gleif_relations/<lei>.json, git-ignored) with the
time it was read, and the folder's files and checksums are recorded in data/reference/supply_datasets.json →
gleif_issuer_relations. Paced at about one request a second; a 429 or a server error waits and retries.

Usage: venv/bin/python -m scripts.fetch_gleif_relations [--refresh]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = "https://api.gleif.org/api/v1"
HEADERS = {"Accept": "application/vnd.api+json"}
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "gleif_relations"
PACE_S = 1.05


def _get(url: str, params: dict | None = None) -> dict | None:
    for attempt in range(1, 6):
        r = requests.get(url, params=params, headers=HEADERS, timeout=60)
        time.sleep(PACE_S)
        if r.status_code == 404:
            return None
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(15 * attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"{url}: GLEIF did not answer after 5 tries")


def _all(url: str) -> list[dict]:
    out, page = [], 1
    while True:
        d = _get(url, {"page[size]": 200, "page[number]": page})
        if d is None:
            return out
        out += d["data"]
        if page >= d["meta"]["pagination"]["lastPage"]:
            return out
        page += 1


def main() -> int:
    from sqlalchemy import text

    from core.db.session import get_session
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="read again an issuer already held")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    with get_session() as s:
        leis = sorted({r[0].strip().upper() for r in s.execute(text("SELECT lei FROM issuers WHERE lei IS NOT NULL")).all()})
    done = 0
    for lei in leis:
        path = OUT / f"{lei}.json"
        if path.exists() and not a.refresh:
            continue
        rec = _get(f"{BASE}/lei-records/{lei}")
        doc = {"lei": lei, "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "record": rec and rec["data"],
               "ultimate_children": _all(f"{BASE}/lei-records/{lei}/ultimate-children") if rec else [],
               "direct_children": _all(f"{BASE}/lei-records/{lei}/direct-children") if rec else []}
        path.write_text(json.dumps(doc, ensure_ascii=False))
        done += 1
        print(f"  {lei}: {len(doc['ultimate_children'])} ultimate, {len(doc['direct_children'])} direct", flush=True)
    files = [{"file": str(p.relative_to(ROOT)), "bytes": p.stat().st_size,
              "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.glob("*.json"))]
    from scripts.fetch_supply_datasets import record
    record("gleif_issuer_relations", {
        "source": "GLEIF API: each issuer's LEI record and the entities it consolidates (ultimate and direct children)",
        "url": BASE, "approved": "product owner, 2026-10-23 (GLEIF API reads)",
        "licence": "CC0 1.0", "licence_status": "GLEIF's LEI data terms of use: 'The data available through the Access "
                                                "Service are provided under the CC0 licence' (read 2026-10-23)",
        "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": files})
    print({"issuers": len(leis), "read_now": done, "held": len(files)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
