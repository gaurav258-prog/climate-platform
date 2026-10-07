"""UN M49 regions — which countries each continent holds, from the Unicode CLDR's territory containment (CLDR 48.0.0, the
release behind ref_countries; CLDR's containment follows the UN Statistics Division's M49 standard). Adopted by the
product owner on 2026-10-07 to say which countries a continental damage curve covers.

  build()      read the held CLDR file (data/datasets/sources/cldr_<version>_territoryContainment.json) and write
               data/reference/un_m49_regions.json: each region in REGIONS with its ISO 3166 alpha-2 members (nested
               sub-regions expanded; CLDR's '-status-' variants and groupings outside M49 are not read)
  countries()  region code → its members, from that file
  region_of()  ISO alpha-2 → the region in REGIONS holding it, or None
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from services.reference.countries import CLDR_VERSION

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "datasets" / "sources" / f"cldr_{CLDR_VERSION}_territoryContainment.json"
OUT = ROOT / "data" / "reference" / "un_m49_regions.json"
URL = (f"https://raw.githubusercontent.com/unicode-org/cldr-json/{CLDR_VERSION}/cldr-json/cldr-core/supplemental/"
       "territoryContainment.json")
# the M49 regions a continental curve can be assigned to — the five continents, with the Americas as M49 splits them
REGIONS = {"150": "Europe", "021": "Northern America", "419": "Latin America and the Caribbean", "142": "Asia",
           "002": "Africa", "009": "Oceania"}


def _members(tc: dict, code: str, seen: Optional[set] = None) -> set[str]:
    seen = seen if seen is not None else set()
    if code in seen:
        return set()
    seen.add(code)
    out: set[str] = set()
    for c in (tc.get(code) or {}).get("_contains", []):
        if len(c) == 2 and c.isalpha():
            out.add(c)
        else:
            out |= _members(tc, c, seen)
    return out


def build() -> dict:
    raw = SOURCE.read_bytes()
    tc = json.loads(raw)["supplemental"]["territoryContainment"]
    doc = {"basis": "UN M49 regions as the Unicode CLDR's territory containment states them (CLDR "
                    f"{CLDR_VERSION}); the countries of each region, nested sub-regions expanded",
           "source": {"url": URL, "file": str(SOURCE.relative_to(ROOT)), "sha256": hashlib.sha256(raw).hexdigest()},
           "adopted": {"by": "product owner", "date": "2026-10-07",
                       "for": "which countries a continental damage curve covers"},
           "regions": {code: {"name": name, "countries": sorted(_members(tc, code))} for code, name in REGIONS.items()}}
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    _doc.cache_clear()
    return doc


@lru_cache(maxsize=1)
def _doc() -> dict:
    return json.loads(OUT.read_text(encoding="utf-8"))


def countries(code: str) -> list[str]:
    return list(_doc()["regions"][code]["countries"])


def region_of(iso2: str) -> Optional[str]:
    for code, r in _doc()["regions"].items():
        if iso2 in r["countries"]:
            return code
    return None
