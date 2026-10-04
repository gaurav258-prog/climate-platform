"""The region reference (E157): the sub-national units a regional fact may name, from the official lists only.

  ISO 3166-2 subdivisions — data/reference/regions/: each national authority's own list, kept exactly as published,
  with the rule that forms the ISO code from it (provenance.json): US — Census Bureau state FIPS/ANSI codes,
  'US-' + USPS code; BR — IBGE federative units, 'BR-' + sigla. A country without a list here has no named regions.
  NUTS (EU regions) — Eurostat/GISCO NUTS 2021 (data/reference/geo/nuts3_eu_20m_2021.geojson); a NUTS code's parents
  are its prefixes (NUTS-1 three characters, NUTS-2 four), so every level is read from the level-3 file.

A region code is valid only if it is here; a store or reader that names a region checks it with known().
"""
from __future__ import annotations

import csv
import io
import json
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "regions"
NUTS_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "geo" / "nuts3_eu_20m_2021.geojson"


@lru_cache(maxsize=1)
def provenance() -> dict:
    return json.loads((DIR / "provenance.json").read_text(encoding="utf-8"))


def _us(raw: bytes) -> dict[str, str]:
    return {f"US-{r['STUSAB']}": r["STATE_NAME"] for r in csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="|")}


def _br(raw: bytes) -> dict[str, str]:
    return {f"BR-{r['sigla']}": r["nome"] for r in json.loads(raw)}


_READERS = {"US": _us, "BR": _br}


@lru_cache(maxsize=None)
def of_country(cc: str) -> dict[str, str]:
    """{ISO 3166-2 code: name} of a country's subdivisions ({} when no official list is held)."""
    f = provenance()["files"].get(cc)
    return _READERS[cc]((DIR / f["file"]).read_bytes()) if f else {}


@lru_cache(maxsize=1)
def nuts() -> dict[str, str]:
    """{NUTS code: name} — level 3 as published, levels 1 and 2 as the prefixes of the level-3 codes (name '' when the
    file does not carry it)."""
    out: dict[str, str] = {}
    for f in json.loads(NUTS_FILE.read_text(encoding="utf-8"))["features"]:
        p = f["properties"]
        out[p["NUTS_ID"]] = p.get("NUTS_NAME") or ""
        for n in (3, 4):
            out.setdefault(p["NUTS_ID"][:n], "")
    return out


def known(code: str) -> bool:
    """Is this a region code of the reference? ('' — the national figure — is not a region.)"""
    if not code:
        return False
    if "-" in code[:3]:
        return code in of_country(code.split("-", 1)[0])
    return code in nuts()
