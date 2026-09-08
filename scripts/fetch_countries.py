"""Eurostat GISCO world country boundaries (2020, 1:3M, EPSG:4326) → data/reference/geo/countries_world_03m_2020.geojson.gz.

The ONE land layer every map cell is clipped against (services/geo/cells.py): supervisor regions, the agri hex
grid, the site neighbourhood grid, the asset hexagons. Same authoritative source as the NUTS-3 layer.
Public, keyless; 16 MB raw, ~5 MB gzipped, tracked. Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_countries.py
"""
from __future__ import annotations

import gzip
import sys
from pathlib import Path

import requests

URL = "https://gisco-services.ec.europa.eu/distribution/v2/countries/geojson/CNTR_RG_03M_2020_4326.geojson"
OUT = Path("data/reference/geo/countries_world_03m_2020.geojson.gz")


def main() -> int:
    r = requests.get(URL, timeout=300); r.raise_for_status()
    n = len(r.json().get("features", []))
    if n < 200:
        raise RuntimeError(f"country file looks truncated: {n} features")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT, "wb", compresslevel=9) as f:
        f.write(r.content)
    print(f"wrote {OUT}: {n} countries ({OUT.stat().st_size/1e6:.1f} MB gzipped) from Eurostat GISCO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
