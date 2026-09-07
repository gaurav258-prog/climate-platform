"""Eurostat GISCO NUTS-3 boundaries (2021, 1:20M, EPSG:4326) → data/reference/geo/nuts3_eu_20m_2021.geojson.

The regional unit of the supervisor heat map (services/geo/regions.py) — the same NUTS-3 level EBA Pillar 3
Template 5 and ESRS E1-9 use. Public, keyless, ~1.7 MB. The file is tracked in git; re-run to refresh.
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_nuts3.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

URL = "https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_20M_2021_4326_LEVL_3.geojson"
OUT = Path("data/reference/geo/nuts3_eu_20m_2021.geojson")


def main() -> int:
    r = requests.get(URL, timeout=120); r.raise_for_status()
    n = len(r.json().get("features", []))
    if n < 1000:
        raise RuntimeError(f"NUTS-3 file looks truncated: {n} features")
    OUT.parent.mkdir(parents=True, exist_ok=True); OUT.write_bytes(r.content)
    print(f"wrote {OUT}: {n} NUTS-3 regions ({len(r.content)/1e6:.1f} MB) from Eurostat GISCO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
