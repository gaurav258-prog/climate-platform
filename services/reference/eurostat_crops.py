"""Eurostat crop production (apro_cpsh1) — a reviewed yield source (E153), read for every crop of the registry that
states a Eurostat code and every country Eurostat reports (EU-27, EFTA, UK, candidate countries; aggregates such as
EU27_2020 are not countries and are not read). Area and production are Eurostat's (thousands → absolutes); yield is
Eurostat's published yield (EU standard humidity); year-on-year is derived from production.

The 'file' of a release is the set of Eurostat responses for the registry's crops, serialised in a fixed order, so the
same publication gives the same bytes. The cheap check reads the dataset's 'updated' stamp before any full download.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

import requests

from services.reference.yield_sources import store_round

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/apro_cpsh1"
SOURCE = "EUROSTAT apro_cpsh1"
PARSER_VERSION = "eurostat-apro_cpsh1-v1"
MEASURES = {"area": "AR_THS_HA", "prod": "HPRD_HUMD_EU_THS_T", "yield": "YLD_HUMD_EU_T_HA"}
ALIASES = {"EL": "GR", "UK": "GB"}          # Eurostat's codes for Greece and the United Kingdom
_UA = {"User-Agent": "Tellumen reference refresh (+https://tellumen.io)"}


class FetchError(RuntimeError):
    pass


def crops() -> dict[str, str]:
    """{Eurostat crop code: our commodity} from the crop registry."""
    from ml.features.crop_registry import crops as registry
    return {c["eurostat_crop"]: c["commodity"] for c in registry() if c.get("eurostat_crop")}


def countries(session) -> dict[str, str]:
    """{Eurostat geo code: ISO alpha-2} for every country of the country reference (aliases EL→GR, UK→GB)."""
    from sqlalchemy import text
    iso = {r[0].strip() for r in session.execute(text("SELECT iso2 FROM ref_countries WHERE is_country")).all()}
    out = {c: c for c in iso}
    out.update({k: v for k, v in ALIASES.items() if v in iso})
    return out


def reader(country_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    h.update(REGISTRY.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(country_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def _get(params: dict) -> dict:
    try:
        r = requests.get(BASE, params={"format": "JSON", **params}, headers=_UA, timeout=120)
    except requests.RequestException as e:
        raise FetchError(f"Eurostat could not be reached: {e}") from e
    if r.status_code != 200:
        raise FetchError(f"Eurostat answered {r.status_code}")
    return r.json()


def published(last_modified: str | None, etag: str | None) -> dict:
    """The dataset's 'updated' stamp, from the smallest possible query — changed when it differs from the last check."""
    stamp = _get({"crops": next(iter(crops())), "strucpro": MEASURES["area"], "geo": "ES", "lastTimePeriod": "1"}).get("updated")
    return {"changed": stamp is None or stamp != last_modified, "last_modified": stamp, "etag": None}


def download() -> bytes:
    """Every registry crop × measure, all countries — serialised in a fixed order (the release's 'file')."""
    out = {}
    for code in sorted(crops()):
        for field, measure in MEASURES.items():
            out[f"{code}|{field}"] = _get({"crops": code, "strucpro": measure})
    return json.dumps(out, sort_keys=True, separators=(",", ":")).encode()


def _series(doc: dict) -> dict:
    """JSON-stat → {(geo, year): value}; the value map is keyed by a flat index over the dimension sizes."""
    ids, size = doc["id"], doc["size"]
    idx = {d: doc["dimension"][d]["category"]["index"] for d in ids}
    inv = {d: {v: k for k, v in idx[d].items()} for d in ids}
    out = {}
    for flat, val in (doc.get("value") or {}).items():
        rem, coords = int(flat), []
        for n in reversed(size):
            coords.append(rem % n)
            rem //= n
        pos = dict(zip(ids, reversed(coords)))
        out[(inv["geo"][pos["geo"]], int(inv["time"][pos["time"]]))] = float(val)
    return out


@lru_cache(maxsize=4)
def _decode(data: bytes) -> dict:
    return json.loads(data)


def parse(data: bytes, country_map: dict[str, str]) -> list[dict]:
    docs = _decode(data)
    rows = []
    for code, commodity in sorted(crops().items()):
        s = {f: _series(docs[f"{code}|{f}"]) for f in MEASURES if f"{code}|{f}" in docs}
        keys = set().union(*[set(v) for v in s.values()]) if s else set()
        for geo, year in sorted(keys):
            iso = country_map.get(geo)
            if not iso:
                continue                                     # an aggregate (EU27_2020 …) or a code we cannot place
            prod, prev, area = (s.get("prod", {}).get((geo, year)), s.get("prod", {}).get((geo, year - 1)),
                                s.get("area", {}).get((geo, year)))
            rows.append({"commodity": commodity, "country": iso, "season_year": year,
                         "production_tonnes": store_round(prod * 1000, 1) if prod is not None else None,
                         "area_harvested_ha": store_round(area * 1000, 1) if area is not None else None,
                         "yield_tonnes_ha": store_round(s.get("yield", {}).get((geo, year)), 4),
                         "yoy_change_pct": store_round((prod - prev) / prev * 100, 2) if (prod and prev) else None,
                         "note": f"Eurostat apro_cpsh1 crop={code} geo={geo}; yield as published (EU standard humidity)"})
    return rows
