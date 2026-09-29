"""EU member states, from the Eurostat GISCO country layer (its EU_STAT flag) — never a typed list.

GISCO writes Greece as EL and the United Kingdom as UK; `is_member()` takes ISO 3166-1 alpha-2 (GR, GB) or GISCO codes.
The fallback is used only when the layer is not installed.
"""
from __future__ import annotations

import gzip
import json
from functools import lru_cache

from services.geo.cells import COUNTRIES_PATH

_FALLBACK = frozenset("AT BE BG CY CZ DE DK EE EL ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK".split())
_GISCO_TO_ISO = {"EL": "GR", "UK": "GB"}


@lru_cache(maxsize=1)
def members_gisco() -> frozenset:
    """Member states as GISCO codes (EL = Greece)."""
    if not COUNTRIES_PATH.exists():
        return _FALLBACK
    with gzip.open(COUNTRIES_PATH, "rt") as f:
        feats = json.load(f)["features"]
    got = frozenset(x["properties"]["CNTR_ID"] for x in feats if x["properties"].get("EU_STAT") == "T")
    return got or _FALLBACK


@lru_cache(maxsize=1)
def members_iso2() -> frozenset:
    return frozenset(_GISCO_TO_ISO.get(c, c) for c in members_gisco())


def is_member(code: str | None) -> bool:
    c = (code or "").strip().upper()
    return c in members_iso2() or c in members_gisco()
