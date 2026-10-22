"""Fetch the observed global-mean temperature record the warming-level timeline reads (the product owner's approval of
2026-10-22): HadCRUT5, Met Office Hadley Centre / Climatic Research Unit — the global annual summary series of the
analysis (HadCRUT.5.0.2.0), anomalies in °C relative to 1961–1990 with their 95% range. Open Government Licence v3.

The file is small and the server states no size, so it is fetched whole and kept with its SHA-256; a file whose header
is not the summary series' is refused. It is kept as committed reference data (data/reference/climate/sources/hadcrut5,
attribution in data/reference/climate/warming_axis.json) — the axis refuses a file that differs.

    venv/bin/python -m scripts.fetch_hadcrut5
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

URL = ("https://www.metoffice.gov.uk/hadobs/hadcrut5/data/HadCRUT.5.0.2.0/analysis/diagnostics/"
       "HadCRUT.5.0.2.0.analysis.summary_series.global.annual.csv")
HEADER = "Time,Anomaly (deg C),Lower confidence limit (2.5%),Upper confidence limit (97.5%)"
OUT = Path(__file__).resolve().parents[1] / "data" / "reference" / "climate" / "sources" / "hadcrut5"


def main() -> int:
    r = requests.get(URL, timeout=60, headers={"Accept-Encoding": "identity"})
    r.raise_for_status()
    body = r.content
    first = body.decode("utf-8", errors="replace").splitlines()[0].strip()
    if first != HEADER:
        print(f"refused: the file's header is {first!r}, not the summary series' {HEADER!r}")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    name = URL.rsplit("/", 1)[1]
    (OUT / name).write_bytes(body)
    (OUT / "provenance.json").write_text(json.dumps({
        "dataset": "HadCRUT5 analysis, global annual summary series", "version": "HadCRUT.5.0.2.0", "url": URL,
        "publisher": "Met Office Hadley Centre / Climatic Research Unit, University of East Anglia",
        "licence": "Open Government Licence v3", "baseline": "1961-1990", "file": name, "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(), "last_modified": r.headers.get("Last-Modified"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, indent=1))
    print(f"fetched {name}: {len(body)} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
