"""Eurostat crop production by NUTS-2 region (apro_cpshr, EU standard humidity) — a reviewed yield source holding one
series per region (E158), for every crop of the registry that states its regional codes (eurostat_regional).

A crop's regional series is the Eurostat crop it names, or the sum of the crops it names where Eurostat publishes the
total only nationally: wheat by region is 'common wheat and spelt' (C1110) + 'durum wheat' (C1120), the two parts of
'wheat and spelt' (C1100) in Eurostat's crop classification — a region-year is read only when both parts are published.

Regions: NUTS-2 codes of the region reference (NUTS 2021); the country is the code's first two letters (EL → GR,
UK → GB). What the reader sets aside, counted and shown with the release: national and aggregate figures (the national
series is apro_cpsh1's), NUTS-1 figures, extra-regio codes, codes not in NUTS 2021 (regions of earlier or later NUTS
versions), a summed crop with a part not published, an area with no production figure.

Yield is Eurostat's published yield for a crop read from one code; for a summed crop it is production ÷ area.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from services.reference.eurostat_crops import ALIASES, _series, fetch
from services.reference.eurostat_crops import stamp as eurostat_stamp
from services.reference.yield_sources import store_round

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpshr"
SOURCE = "EUROSTAT apro_cpshr"
PARSER_VERSION = "eurostat-apro_cpshr-v1"
MEASURES = {"area": "AR_THS_HA", "prod": "HPRD_HUMD_EU_THS_T", "yield": "YLD_HUMD_EU_T_HA"}


def crops() -> dict[str, list[str]]:
    """{our commodity: [Eurostat crop codes summed]} from the crop registry."""
    from ml.features.crop_registry import crops as registry
    return {c["commodity"]: list(c["eurostat_regional"]) for c in registry() if c.get("eurostat_regional")}


def countries(session) -> dict[str, str]:
    """{NUTS-2 code: ISO alpha-2 country} for every NUTS-2 region of the region reference whose country is a country
    of the country reference."""
    from sqlalchemy import text

    from services.reference import regions
    iso = {r[0].strip() for r in session.execute(text("SELECT iso2 FROM ref_countries WHERE is_country")).all()}
    out = {}
    for code in regions.nuts():
        cc = ALIASES.get(code[:2], code[:2])
        if len(code) == 4 and cc in iso:
            out[code] = cc
    return out


def reader(region_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    h.update(REGISTRY.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(region_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def _codes() -> list[str]:
    return sorted({code for codes in crops().values() for code in codes})


def published(last_modified: str | None, etag: str | None) -> dict:
    """The dataset's 'updated' stamp, from the smallest possible query — changed when it differs from the last check."""
    stamp = fetch(BASE, {"crops": _codes()[0], "strucpro": MEASURES["area"], "geo": "ES61",
                         "lastTimePeriod": "1"}).get("updated")
    return {"changed": stamp is None or stamp != last_modified, "last_modified": stamp, "etag": None}


def download() -> bytes:
    """Every regional crop code × measure, all regions — serialised in a fixed order (the release's 'file')."""
    out = {}
    for code in _codes():
        for field, measure in MEASURES.items():
            out[f"{code}|{field}"] = fetch(BASE, {"crops": code, "strucpro": measure})
    return json.dumps(out, sort_keys=True, separators=(",", ":")).encode()


def stamp(data: bytes) -> str | None:
    """Eurostat's own 'updated' stamp, read from the data as for the national dataset."""
    return eurostat_stamp(data)


def _why_not_a_region(geo: str, region_map: dict[str, str]) -> str | None:
    if len(geo) != 4 or geo.startswith(("EU", "EA")):
        return "a national or aggregate figure (national series are read from apro_cpsh1)" if len(geo) != 3 \
            else "a NUTS-1 figure (regional series are read at NUTS-2)"
    if geo.endswith("ZZ"):
        return "extra-regio (not a territory)"
    if geo not in region_map:
        return "not a NUTS 2021 region (a region of an earlier or later NUTS version)"
    return None


@lru_cache(maxsize=2)
def _read(data: bytes, regions_: tuple[tuple[str, str], ...]) -> tuple[list[dict], dict[str, int]]:
    docs, region_map = json.loads(data), dict(regions_)
    aside: dict[str, int] = {}

    def skip(why: str) -> None:
        aside[why] = aside.get(why, 0) + 1

    rows = []
    for commodity, codes in sorted(crops().items()):
        s = {code: {f: _series(docs[f"{code}|{f}"]) for f in MEASURES if f"{code}|{f}" in docs} for code in codes}
        keys = sorted({k for parts in s.values() for series in parts.values() for k in series})
        prod_of: dict = {}
        for geo, year in keys:
            why = _why_not_a_region(geo, region_map)
            if why:
                skip(why)
                continue
            vals = {f: [s[c].get(f, {}).get((geo, year)) for c in codes] for f in ("prod", "area")}
            if len(codes) > 1 and any(None in v and any(x is not None for x in v) for v in vals.values()):
                skip("a summed crop with a part not published for the region and year")
                continue
            prod = sum(vals["prod"]) * 1000 if None not in vals["prod"] else None
            area = sum(vals["area"]) * 1000 if None not in vals["area"] else None
            if prod is None:
                if area is not None:
                    skip("an area with no production figure")
                continue
            prod_of[(geo, year)] = prod
            yld = s[codes[0]].get("yield", {}).get((geo, year)) if len(codes) == 1 else (prod / area if area else None)
            rows.append({"commodity": commodity, "country": region_map[geo], "region_code": geo, "season_year": year,
                         "production_tonnes": store_round(prod, 1), "area_harvested_ha": store_round(area, 1),
                         "yield_tonnes_ha": store_round(yld, 4),
                         "note": f"Eurostat apro_cpshr crops={'+'.join(codes)} geo={geo}; EU standard humidity; "
                                 + ("yield as published" if len(codes) == 1 else "yield = production ÷ area")})
        for r in rows:
            if r["commodity"] == commodity:
                prev = prod_of.get((r["region_code"], r["season_year"] - 1))
                cur = prod_of[(r["region_code"], r["season_year"])]
                r["yoy_change_pct"] = store_round((cur - prev) / prev * 100, 2) if prev else None
    return rows, dict(sorted(aside.items()))


def parse(data: bytes, region_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(region_map.items())))[0]


def set_aside(data: bytes, region_map: dict[str, str]) -> dict[str, int]:
    return _read(data, tuple(sorted(region_map.items())))[1]
