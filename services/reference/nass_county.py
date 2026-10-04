"""USDA NASS Quick Stats by county — a reviewed yield source with one series per US county (E161).

The same series, units and key handling as the state source (services.reference.nass_quickstats: the registry's exact
short_desc per crop, units only from data/reference/nass_quickstats.json, the key never shown), at aggregation level
COUNTY, SURVEY, annual 'YEAR'. NASS publishes county estimates once a year, after its annual summary — so a county
figure is never a forecast of a season in progress. Its own source and release: one release a year, apart from the
monthly state and national ones.

A county is named 'US-IA-19001' — its state's ISO 3166-2 code and its 5-digit FIPS code — and read only when it is in
the Census Bureau's 2020 county list (region reference). Set aside, counted and shown with the release: NASS's
'OTHER (COMBINED) COUNTIES' (county code 998), counties not in the 2020 list (renamed or dissolved since), values NASS
does not give as a number ('(D)' …), and an area with no production figure for the year.

The release's file keeps, for each NASS record, its identifying and value fields (the full record repeats ~40 fields
over 1.27 million records); which fields are kept is part of this reader's version.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from services.reference import nass_quickstats as N
from services.reference.yield_sources import store_round

SOURCE = "USDA NASS Quick Stats (county)"
BASE = N.BASE
PARSER_VERSION = "usda-nass-county-v1"
FetchError = N.FetchError
_FILTER = [("source_desc", "SURVEY"), ("freq_desc", "ANNUAL"), ("domain_desc", "TOTAL"),
           ("agg_level_desc", "COUNTY"), ("reference_period_desc", "YEAR")]
_KEEP = ("short_desc", "state_alpha", "state_ansi", "county_ansi", "county_code", "county_name", "year", "Value",
         "load_time", "unit_desc")
_COMBINED = "998"


def countries(session) -> dict[str, str]:
    """{NASS location 'IA19001' (state_alpha + state and county FIPS): 'US-IA-19001'} for every county of the region
    reference."""
    from services.reference import regions
    return {code[3:5] + code[6:]: code for code in regions.counties("US")}


def reader(location_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    for p in (N.REF, REGISTRY):
        h.update(p.read_bytes())
    h.update(",".join(_KEEP).encode())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(location_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def published(last_modified: str | None, etag: str | None) -> dict:
    """Has NASS loaded any county record of the registry's series since the last release's stamp? One count."""
    if not last_modified:
        return {"changed": True, "last_modified": None, "etag": None}
    n = N._count([*[("short_desc", d) for d in sorted(N.crops())], *_FILTER, ("load_time__GT", last_modified)])
    return {"changed": n > 0, "last_modified": last_modified, "etag": None}


def stamp(data: bytes) -> str | None:
    """NASS's own stamp: the latest load_time among the county records downloaded."""
    times = [r["load_time"] for part in json.loads(data)["data"].values() for r in part]
    return max(times) if times else None


def download() -> bytes:
    """Every registry series, state by state (a Quick Stats answer holds at most 50,000 records): the states that hold
    county records of the series are asked first, then each state's records — kept fields only, in a fixed order."""
    out: dict = {}
    for desc in sorted(N.crops()):
        q = [("short_desc", desc), *_FILTER]
        states = sorted(N._get("get_param_values", [*q, ("param", "state_alpha")]).get("state_alpha", [])) \
            if N._count(q) else []
        for st in states:
            rows = N._get("api_GET", [*q, ("state_alpha", st)])["data"]
            out[f"{desc}|{st}"] = sorted(({k: r.get(k, "") for k in _KEEP} for r in rows),
                                         key=lambda r: (r["state_ansi"], r["county_code"], r["year"], r["load_time"]))
    return json.dumps({"data": out}, sort_keys=True, separators=(",", ":")).encode()


@lru_cache(maxsize=2)
def _read(data: bytes, locations: tuple[tuple[str, str], ...]) -> tuple[list[dict], dict[str, int]]:
    ref, by_desc, location_map = N.reference(), N.crops(), dict(locations)
    aside: dict[str, int] = {}

    def skip(why: str) -> None:
        aside[why] = aside.get(why, 0) + 1

    vals: dict = {}
    for key, rows in json.loads(data)["data"].items():
        desc = key.rsplit("|", 1)[0]
        if desc not in by_desc:
            continue
        commodity, field = by_desc[desc]
        for r in rows:
            if r["county_code"] == _COMBINED:
                skip("NASS's combined counties (OTHER (COMBINED) COUNTIES), not a county")
                continue
            code = location_map.get(r["state_alpha"] + r["state_ansi"] + r["county_ansi"])
            if code is None:
                skip("not a county of the Census Bureau's 2020 county list (renamed or dissolved since)")
                continue
            v = N._number(r["Value"])
            if v is None:
                skip(f"not given as a number ({r['Value'].strip()})")
                continue
            vals.setdefault((commodity, code, int(r["year"])), {})[field] = v * N._factor(ref, commodity, field,
                                                                                            r["unit_desc"])
    out = []
    for (commodity, code, year), v in sorted(vals.items()):
        prod, area = v.get("prod"), v.get("area")
        if prod is None:
            if area is not None:
                skip("area without a production estimate for the year")
            continue
        prev = vals.get((commodity, code, year - 1), {}).get("prod")
        out.append({"commodity": commodity, "country": "US", "region_code": code, "season_year": year,
                    "production_tonnes": store_round(prod, 1), "area_harvested_ha": store_round(area, 1),
                    "yield_tonnes_ha": store_round(prod / area, 4) if area else None,
                    "yoy_change_pct": store_round((prod - prev) / prev * 100, 2) if prev else None,
                    "note": "USDA NASS Quick Stats SURVEY county estimate, annual 'YEAR'; definition per the crop "
                            "registry's nass_label; yield = production ÷ area"})
    return out, dict(sorted(aside.items()))


def parse(data: bytes, location_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(location_map.items())))[0]


def set_aside(data: bytes, location_map: dict[str, str]) -> dict[str, int]:
    return _read(data, tuple(sorted(location_map.items())))[1]
