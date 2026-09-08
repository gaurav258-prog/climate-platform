"""EU member states as coded in the Eurostat GISCO country layer (EL = Greece). Read from the layer when present."""
from __future__ import annotations

import gzip
import json
from functools import lru_cache

from services.geo.cells import COUNTRIES_PATH

_FALLBACK = frozenset("AT BE BG CY CZ DE DK EE EL ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split())


@lru_cache(maxsize=1)
def _members() -> frozenset:
    if not COUNTRIES_PATH.exists():
        return _FALLBACK
    with gzip.open(COUNTRIES_PATH, "rt") as f:
        feats = json.load(f)["features"]
    got = frozenset(x["properties"]["CNTR_ID"] for x in feats if x["properties"].get("EU_STAT") == "T")
    return got or _FALLBACK


EU_MEMBERS = _members()
