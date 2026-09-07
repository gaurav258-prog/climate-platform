"""Region → representative point: how a supervisor's shadow book gets a location from AnaCredit-style data.

Supervisory granular data carries a collateral REGION (NUTS-3 code, or a postcode), not coordinates. We resolve:
  • NUTS-3 code  → the region's representative point (Eurostat GISCO 2021 polygons, shapely representative_point)
  • postcode     → NUTS-3 via Eurostat TERCET correspondence tables (pc2020_<CC>_NUTS-2021), then as above
  • country only → the country's largest NUTS-3 by area? NO — that would fabricate a location. Country-only rows
                   stay UNLOCATED and are reported as such.
Every resolved point carries a `location_precision` label ('nuts3' | 'postcode→nuts3') that travels with the
asset and onto every figure derived from it. TERCET tables are fetched on demand (public, keyless) into
data/reference/geo/tercet/ (gitignored) — scripts/fetch_nuts3.py documents the GISCO source for the polygons.
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Optional

from services.geo.regions import NUTS3_PATH

TERCET_DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "geo" / "tercet"
TERCET_URL = "https://gisco-services.ec.europa.eu/tercet/NUTS-2021/pc2020_{cc}_NUTS-2021_v{v}.zip"
TERCET_VERSIONS = ("1.0", "2.0", "3.0", "4.0")


@lru_cache(maxsize=1)
def _nuts3() -> dict:
    """NUTS_ID → {name, country, point (lat, lon)}."""
    from shapely.geometry import shape
    out = {}
    if not NUTS3_PATH.exists():
        return out
    for f in json.loads(NUTS3_PATH.read_text())["features"]:
        p = f["properties"]; g = shape(f["geometry"]); rp = g.representative_point()
        out[p["NUTS_ID"]] = {"name": p["NUTS_NAME"], "country": p["CNTR_CODE"], "lat": round(rp.y, 5), "lon": round(rp.x, 5)}
    return out


def nuts3_point(code: str) -> Optional[dict]:
    r = _nuts3().get((code or "").strip().upper())
    return {**r, "nuts3": code.strip().upper(), "location_precision": "nuts3"} if r else None


def _tercet_path(cc: str) -> Path:
    return TERCET_DIR / f"pc2020_{cc}_NUTS-2021.csv"


def fetch_tercet(cc: str) -> Optional[Path]:
    """Download the postcode→NUTS-3 table for a country (version fallback; the archive's version differs per country)."""
    import requests
    p = _tercet_path(cc)
    if p.exists():
        return p
    for v in TERCET_VERSIONS:
        r = requests.get(TERCET_URL.format(cc=cc, v=v), timeout=60)
        if r.status_code == 200 and r.content[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(r.content))
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            TERCET_DIR.mkdir(parents=True, exist_ok=True)
            p.write_bytes(z.read(name))
            return p
    return None


@lru_cache(maxsize=64)
def _postcodes(cc: str) -> dict:
    p = fetch_tercet(cc)
    if p is None:
        return {}
    out = {}
    txt = p.read_text(encoding="utf-8-sig")
    for row in csv.DictReader(io.StringIO(txt), delimiter=";"):
        code = (row.get("CODE") or "").strip().strip("'")
        nuts = (row.get("NUTS3") or "").strip().strip("'")
        if code and nuts:
            out[code] = nuts
    return out


def postcode_point(cc: str, postcode: str) -> Optional[dict]:
    cc = (cc or "").strip().upper(); pc = (postcode or "").strip().replace(" ", "")
    if not cc or not pc:
        return None
    nuts = _postcodes(cc).get(pc) or _postcodes(cc).get(pc.upper())
    if not nuts:
        return None
    r = nuts3_point(nuts)
    return {**r, "postcode": pc, "location_precision": "postcode→nuts3"} if r else None


def resolve(country: Optional[str], nuts3: Optional[str] = None, postcode: Optional[str] = None) -> Optional[dict]:
    """Best available region point, or None (country-only rows are honestly unlocated)."""
    if nuts3:
        r = nuts3_point(nuts3)
        if r:
            return r
    if country and postcode:
        return postcode_point(country, postcode)
    return None
