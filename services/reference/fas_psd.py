"""USDA FAS Production, Supply and Distribution (PSD) — a reviewed yield source (E155): official estimates for the
current and recent market years worldwide, ahead of FAOSTAT's 1–2 year lag. Read for every crop of the registry with
a FAS commodity code (data/reference/crop_registry.json; where FAS's definition differs from FAO's — milled rice,
oils, shelled almonds — fas_label says so) and every country FAS reports (FIPS codes matched through GENC to ISO;
regions and the 'European Union' entity are not countries). Units are converted only by the units table in
data/reference/fas_psd.json; an unknown unit is refused.

The key (api.data.gov, settings.USDA_FAS_API_KEY) is read from the environment and sent in the X-Api-Key header —
never in a URL that could be logged, never stored.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import requests

from services.reference.yield_sources import store_round

REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "fas_psd.json"
PARSER_VERSION = "usda-fas-psd-v1"


class FetchError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


SOURCE = "USDA FAS PSD"
BASE = "https://api.fas.usda.gov/api/psd"


def crops() -> dict[str, str]:
    from ml.features.crop_registry import crops as registry
    return {c["fas_commodity"]: c["commodity"] for c in registry() if c.get("fas_commodity")}


def countries(session) -> dict[str, str]:
    """{ISO alpha-3: alpha-2} for every country of the country reference — FAS's GENC codes are matched to it."""
    from sqlalchemy import text
    return {r[0].strip(): r[1].strip() for r in session.execute(text(
        "SELECT iso3, iso2 FROM ref_countries WHERE iso3 IS NOT NULL AND is_country")).all()}


def reader(country_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    for p in (REF, REGISTRY):
        h.update(p.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(country_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def _get(path: str):
    from core.config import settings
    if not settings.USDA_FAS_API_KEY:
        raise FetchError("USDA_FAS_API_KEY is not set — the api.data.gov key goes in the environment (.env)")
    try:
        r = requests.get(f"{BASE}/{path}", headers={"X-Api-Key": settings.USDA_FAS_API_KEY,
                                                    "User-Agent": "Tellumen reference refresh"}, timeout=120)
    except requests.RequestException as e:
        raise FetchError(f"USDA FAS could not be reached: {e}") from e
    if r.status_code != 200:
        raise FetchError(f"USDA FAS answered {r.status_code} for {path}")
    return r.json()


def published(last_modified: str | None, etag: str | None) -> dict:
    """The latest release month across the registry's FAS commodities — changed when it differs from the last check."""
    stamps = [f"{d['releaseYear']}-{d['releaseMonth']}" for code in sorted(crops())
              for d in _get(f"commodity/{code}/dataReleaseDates")]
    stamp = max(stamps) if stamps else None
    return {"changed": stamp is None or stamp != last_modified, "last_modified": stamp, "etag": None}


def download() -> bytes:
    """FAS's country list and every registry commodity × market year from the first year on — in a fixed order."""
    last = date.today().year + 1
    out = {"countries": sorted(_get("countries"), key=lambda c: c["countryCode"]), "data": {}}
    for code in sorted(crops()):
        for year in range(int(reference()["first_market_year"]), last + 1):
            rows = _get(f"commodity/{code}/country/all/year/{year}")
            out["data"][f"{code}|{year}"] = sorted(rows, key=lambda r: (r["countryCode"], r["attributeId"]))
    return json.dumps(out, sort_keys=True, separators=(",", ":")).encode()


def parse(data: bytes, country_map: dict[str, str]) -> list[dict]:
    doc = json.loads(data)
    ref = reference()
    attr = {v: k for k, v in ref["attributes"].items()}          # attributeId → 'area' | 'prod' | 'yield'
    units = ref["units"]
    iso_of = {c["countryCode"]: country_map.get(c["gencCode"]) for c in doc["countries"] if c.get("gencCode")}
    vals: dict = {}
    for key, rows in doc["data"].items():
        code = key.split("|", 1)[0]
        commodity = crops().get(code)
        if commodity is None:
            continue
        for r in rows:
            field = attr.get(r["attributeId"])
            iso = iso_of.get(r["countryCode"])
            if field is None or iso is None:
                continue                                         # another attribute, or not a country
            u = units.get(str(r["unitId"]))
            if u is None:
                raise FetchError(f"{commodity} {r['countryCode']} {r['marketYear']}: unit {r['unitId']} is not in "
                                 "data/reference/fas_psd.json — refused, never guessed")
            if u["dim"] != ref["field_dims"][field]:
                continue                                         # a known unit of another kind (trees for area): not read
            factor = u["factor"]
            vals.setdefault((commodity, iso, int(r["marketYear"])), {})[field] = float(r["value"]) * factor
    out = []
    for (commodity, iso, year), v in sorted(vals.items()):
        prod, area = v.get("prod"), v.get("area")
        if prod is None and area is None:
            continue
        prev = vals.get((commodity, iso, year - 1), {}).get("prod")
        yld = v.get("yield") if v.get("yield") is not None else (prod / area if (prod and area) else None)
        out.append({"commodity": commodity, "country": iso, "season_year": year,
                    "production_tonnes": store_round(prod, 1), "area_harvested_ha": store_round(area, 1),
                    "yield_tonnes_ha": store_round(yld, 4),
                    "yoy_change_pct": store_round((prod - prev) / prev * 100, 2) if (prod and prev) else None,
                    "note": "USDA FAS PSD — MARKET year; definition per the crop registry's fas_label"})
    return out
