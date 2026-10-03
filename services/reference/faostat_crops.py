"""FAOSTAT crop production — fetching the publisher's file and reading it (E148). Landing is not done here: a file
becomes a release that is reviewed before it reaches the store (services.reference.crop_releases).

  file     Production_Crops_Livestock_E_All_Data_(Normalized).zip (~34 MB), FAO, CC BY 4.0
  mapping  crops: data/reference/crop_registry.json (fao_item); areas: every area whose UN M49 code is a current ISO
           3166 numeric code (ref_countries) is that country, FAO 5000 is the World — data/reference/faostat_crops.json

Two traps, both silent (kept from scripts/ingest_crop_yield_faostat.py, where they were found):
  * encoding — the CSV is UTF-8; read as latin-1 "Côte d'Ivoire" stops matching and ~45 % of world cocoa vanishes;
    areas are matched on FAO's numeric code, never the display name
  * season vs calendar year — FAO reports calendar years; stored as-is and said so in each row's note
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from functools import lru_cache
from pathlib import Path

from services.reference.yield_sources import store_round

REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "faostat_crops.json"
NOTE = "FAOSTAT QCL, FAO CALENDAR year (not a split crop season); yield derived = production/area"
_UA = {"User-Agent": "Tellumen reference refresh (+https://tellumen.io)"}


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


def source() -> str:
    return reference()["store_source"]


def url() -> str:
    return reference()["url"]


class FetchError(RuntimeError):
    pass


def published(last_modified: str | None, etag: str | None, timeout: int = 60) -> dict:
    """Ask the publisher whether its file changed (HEAD): {changed, last_modified, etag}. No validators held → changed."""
    import requests
    try:
        r = requests.head(url(), headers=_UA, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise FetchError(f"FAOSTAT could not be reached: {e}") from e
    if r.status_code >= 400:
        raise FetchError(f"FAOSTAT answered {r.status_code} to the file check")
    lm, et = r.headers.get("Last-Modified"), r.headers.get("ETag")
    same = (et and et == etag) or (not et and lm and lm == last_modified)
    return {"changed": not same, "last_modified": lm, "etag": et}


def download(timeout: int = 900) -> bytes:
    import requests
    try:
        r = requests.get(url(), headers=_UA, timeout=timeout)
    except requests.RequestException as e:
        raise FetchError(f"FAOSTAT could not be reached: {e}") from e
    if r.status_code != 200 or not r.content:
        raise FetchError(f"FAOSTAT answered {r.status_code} to the download")
    return r.content


PARSER_VERSION = "faostat-m49-registry-v1"


def reader(countries: dict[str, str]) -> str:
    """The fingerprint of how a file is read (E151): the parser version, the mapping files and the country set. The
    same file under another reader is another release."""
    import hashlib

    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    for path in (REF, REGISTRY):
        h.update(path.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(countries.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def iso_by_m49(session) -> dict[str, str]:
    """{ISO 3166 numeric code: alpha-2} from the country reference — the countries FAOSTAT areas are matched to."""
    from sqlalchemy import text
    return {r[0].strip(): r[1].strip() for r in session.execute(text(
        "SELECT numeric_code, iso2 FROM ref_countries WHERE numeric_code IS NOT NULL AND is_country")).all()}


def parse(zip_bytes: bytes, countries: dict[str, str]) -> list[dict]:
    """The publisher's file → our rows: {commodity, country, season_year, production_tonnes, area_harvested_ha,
    yield_tonnes_ha, yoy_change_pct, note}, for the registry's crops in every country (countries = {ISO numeric:
    alpha-2}, iso_by_m49) and the World; regional aggregates and former states are not countries and are not read."""
    from ml.features.crop_registry import fao_items
    ref = reference()
    if not countries:
        raise FetchError("the country reference is empty — load it (feed reference_countries) before reading FAOSTAT")
    item_to_commodity = fao_items()
    world = int(ref["world_area_code"])
    elements = ref["elements"]

    def country_of(rec) -> str | None:
        try:
            if int(rec["Area Code"]) == world:
                return "WLD"
        except ValueError:
            return None
        return countries.get((rec.get("Area Code (M49)") or "").lstrip("'").strip().zfill(3))
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as e:
        raise FetchError("the FAOSTAT file is not a zip archive") from e
    members = [n for n in z.namelist() if n.endswith("(Normalized).csv")]
    if not members:
        raise FetchError("the FAOSTAT archive holds no '(Normalized).csv'")
    raw: dict = {}
    with z.open(members[0]) as f:
        for rec in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="strict")):
            commodity = item_to_commodity.get(rec["Item"])
            field = elements.get(rec["Element"])
            if not commodity or not field or not rec["Value"]:
                continue
            iso = country_of(rec)
            if iso:
                raw.setdefault((commodity, iso, int(rec["Year"])), {})[field] = float(rec["Value"])
    db = store_round                                  # one rounding rule for every source (yield_sources)

    series: dict = {}
    for (c, geo, yr), v in raw.items():
        series.setdefault((c, geo), {})[yr] = v.get("prod")
    out = []
    for (c, geo, yr), v in sorted(raw.items()):
        prod, prev, area = v.get("prod"), series[(c, geo)].get(yr - 1), v.get("area")
        out.append({"commodity": c, "country": geo, "season_year": yr,
                    "production_tonnes": db(prod, 1), "area_harvested_ha": db(area, 1),
                    "yield_tonnes_ha": db(prod / area, 4) if (prod and area) else None,
                    "yoy_change_pct": db((prod - prev) / prev * 100, 2) if (prod and prev) else None,
                    "note": NOTE})
    return out
