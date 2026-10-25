"""Fetch the EEA's register of industrial sites (Industrial Reporting under the Industrial Emissions Directive 2010/75/EU
and the E-PRTR Regulation (EC) No 166/2006) — approved by the product owner on 2026-10-23: every production facility of
the latest reporting year, with its coordinates and the parent company the reporting country states (name only; the
register carries no company identifier). Read from the EEA's public SQL service (Discodata, [IED].[latest]).

Licence (the register's catalogue records, EEA SDI 657ac3cb-… and 3bbf28cb-…, version 16.0, February 2026): 'License
CC-BY 4.0 (https://creativecommons.org/licenses/by/4.0/). Copyright holder: European Environment Agency (EEA).'

The query, the rows it returned and the file's sha-256 are recorded in data/reference/supply_datasets.json →
eea_industrial_sites; the rows land in their own folder (data/datasets/eea_industrial_sites, git-ignored) and are read
later only from outside it. Refuses when the rows exceed --max-rows (the approved order of size).

Usage: venv/bin/python -m scripts.fetch_eea_industrial_sites --max-rows 70000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SQL = "https://discodata.eea.europa.eu/sql"
TABLE = "[IED].[latest].[ProductionFacility]"
COLUMNS = ("id", "localId", "siteId", "facilityName", "parentCompanyName", "parentCompanyURL", "status", "countryCode",
           "x_4326", "y_4326", "EPRTRAnnexIMainActivity", "facilityType", "city", "postalCode", "reportingYear")
PAGE = 20000
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "eea_industrial_sites"


def query(sql: str, page: int = 1, size: int = PAGE) -> list[dict]:
    for attempt in range(1, 4):
        try:
            r = requests.get(SQL, params={"query": sql, "p": page, "nrOfHits": size}, timeout=180)
            r.raise_for_status()
            return r.json()["results"]
        except (requests.RequestException, ValueError, KeyError):
            if attempt == 3:
                raise
            time.sleep(10 * attempt)
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, required=True)
    a = ap.parse_args()
    year = query(f"SELECT MAX(reportingYear) AS y FROM {TABLE}")[0]["y"]
    n = query(f"SELECT COUNT(*) AS n FROM {TABLE} WHERE reportingYear = {int(year)}")[0]["n"]
    print(f"reporting year {year}: {n} facilities", flush=True)
    if n > a.max_rows:
        print(f"{n} rows, above the approved {a.max_rows} — refused")
        return 2
    sql = f"SELECT {', '.join(COLUMNS)} FROM {TABLE} WHERE reportingYear = {int(year)} ORDER BY id"
    rows: list[dict] = []
    page = 1
    while len(rows) < n:
        got = query(sql, page)
        if not got:
            break
        rows += got
        page += 1
    if len(rows) != n or len({r["id"] for r in rows}) != n:
        print(f"refused: {len(rows)} rows read ({len({r['id'] for r in rows})} distinct) for a count of {n}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"ProductionFacility_RY{year}.json"
    path.write_text(json.dumps(rows, ensure_ascii=False))
    from scripts.fetch_supply_datasets import record
    record("eea_industrial_sites", {
        "source": "EEA Industrial Reporting under the IED 2010/75/EU and E-PRTR Regulation (EC) No 166/2006 — "
                  "production facilities (Discodata, [IED].[latest])",
        "url": SQL, "query": sql, "reporting_year": year, "rows": n,
        "approved": "product owner, 2026-10-23 (one query of the latest reporting year)",
        "licence": "CC BY 4.0",
        "licence_status": "the register's catalogue records (EEA SDI, version 16.0, February 2026): 'License CC-BY 4.0 "
                          "(https://creativecommons.org/licenses/by/4.0/). Copyright holder: European Environment "
                          "Agency (EEA).'",
        "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [{"file": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]})
    print({"rows": n, "file": str(path.relative_to(ROOT))}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
