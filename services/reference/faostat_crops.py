"""FAOSTAT crop production — fetching the publisher's file and reading it (E148). Landing is not done here: a file
becomes a release that is reviewed before it reaches the store (services.reference.crop_releases).

  file     Production_Crops_Livestock_E_All_Data_(Normalized).zip (~34 MB), FAO, CC BY 4.0
  mapping  data/reference/faostat_crops.json — our commodity per FAO item, ISO-2 per FAO numeric area code

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
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path

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


def parse(zip_bytes: bytes) -> list[dict]:
    """The publisher's file → our rows: {commodity, country, season_year, production_tonnes, area_harvested_ha,
    yield_tonnes_ha, yoy_change_pct, note}, for the mapped commodities and origins (aggregates other than WLD
    excluded by the mapping)."""
    ref = reference()
    item_to_commodity = {i["fao_item"]: i["commodity"] for i in ref["items"]}
    area_to_iso = {a["fao_area_code"]: a["iso2"] for a in ref["areas"]}
    elements = ref["elements"]
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
            try:
                iso = area_to_iso.get(int(rec["Area Code"]))
            except ValueError:
                continue
            if iso:
                raw.setdefault((commodity, iso, int(rec["Year"])), {})[field] = float(rec["Value"])
    def db(x: float | None, places: int) -> float | None:
        """Rounded exactly as Postgres stores a float sent to numeric(…, places): the float as written (its shortest
        decimal form, which is what the driver sends), then half away from zero. Python's round() works on the binary
        value (1563.35 → 1563.3; Postgres 1563.4); one rule for every field, so the same file is the same rows."""
        if x is None:
            return None
        return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))

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
