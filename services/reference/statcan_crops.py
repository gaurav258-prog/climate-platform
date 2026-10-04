"""Statistics Canada table 32-10-0359-01 (field crops: area, yield, production) — a reviewed yield source holding the
Canada series and one series per province (E160), for every crop of the registry that names its StatCan crop
(statcan_crop — the table's exact 'Type of crop' member).

Read as published, in metric units: 'Harvested area (hectares)', 'Production (metric tonnes)' and 'Average yield
(kilograms per hectare)' (÷ 1,000 → t/ha). Geography by StatCan's DGUID: Canada (code 11124) is the national figure; a
province or territory (schema 0002) is named by the ISO 3166-2 code Statistics Canada states for its SGC code (region
reference, SGC 2021 Table B); the aggregates (Maritime provinces, Prairie provinces, East, West) are not regions.

What the reader sets aside, counted and shown with the release:
  * a value StatCan does not publish ('..' not available, 'F' too unreliable, 'x' suppressed)
  * an aggregate of provinces
  * the season in progress: StatCan's crop year runs to the November survey, which gives final production (table
    note 1); its July and September figures are model-based estimates (notes 45, 46). So a figure for the year of the
    file's release, in a file released before December, is the season in progress — read once the November survey
    is published. The release date is the file's own (the date of the table in the zip).
  * an area with no production figure for the year
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import zipfile
from functools import lru_cache

from services.reference.yield_sources import store_round

SOURCE = "STATCAN 32-10-0359-01"
BASE = "https://www150.statcan.gc.ca/n1/tbl/csv/32100359-eng.zip"
TABLE = "32100359.csv"
PARSER_VERSION = "statcan-32100359-v1"
MEASURES = {"Harvested area (hectares)": "area", "Production (metric tonnes)": "prod",
            "Average yield (kilograms per hectare)": "yield"}
NOT_PUBLISHED = {"..": "not available", "F": "too unreliable to be published", "x": "suppressed (confidentiality)"}
_CANADA = re.compile(r"^\d{4}A000011124$")
_PROVINCE = re.compile(r"^\d{4}A0002(\d{2})$")
_UA = {"User-Agent": "Tellumen reference refresh (+https://tellumen.io)"}


class FetchError(RuntimeError):
    pass


def crops() -> dict[str, str]:
    """{StatCan 'Type of crop': our commodity} from the crop registry."""
    from ml.features.crop_registry import crops as registry
    return {c["statcan_crop"]: c["commodity"] for c in registry() if c.get("statcan_crop")}


def countries(session) -> dict[str, str]:
    """{SGC province/territory code: ISO 3166-2 code}, as Statistics Canada states them (region reference)."""
    from services.reference import regions
    return regions.ca_sgc_codes()


def reader(province_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    h.update(REGISTRY.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(province_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def published(last_modified: str | None, etag: str | None, timeout: int = 60) -> dict:
    """Ask StatCan whether the table's file changed (HEAD): {changed, last_modified, etag}. No validators held → changed."""
    import requests
    try:
        r = requests.head(BASE, headers=_UA, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise FetchError(f"Statistics Canada could not be reached: {e}") from e
    if r.status_code >= 400:
        raise FetchError(f"Statistics Canada answered {r.status_code} to the file check")
    lm, et = r.headers.get("Last-Modified"), r.headers.get("ETag")
    same = (et and et == etag) or (not et and lm and lm == last_modified)
    return {"changed": not same, "last_modified": lm, "etag": et}


def download(timeout: int = 600) -> bytes:
    import requests
    try:
        r = requests.get(BASE, headers=_UA, timeout=timeout)
    except requests.RequestException as e:
        raise FetchError(f"Statistics Canada could not be reached: {e}") from e
    if r.status_code != 200 or not r.content:
        raise FetchError(f"Statistics Canada answered {r.status_code} to the download")
    return r.content


def _released(z: zipfile.ZipFile) -> tuple[int, int, int]:
    """The table's release date as the file carries it (the zip entry of the table) — for the season-in-progress rule;
    the release's stamp is the file's HTTP validators (published), as for FAOSTAT."""
    return z.getinfo(TABLE).date_time[:3]


@lru_cache(maxsize=2)
def _read(data: bytes, provinces: tuple[tuple[str, str], ...]) -> tuple[list[dict], dict[str, int]]:
    by_crop, province_map = crops(), dict(provinces)
    z = zipfile.ZipFile(io.BytesIO(data))
    ry, rm, _ = _released(z)
    aside: dict[str, int] = {}

    def skip(why: str) -> None:
        aside[why] = aside.get(why, 0) + 1

    vals: dict = {}
    with z.open(TABLE) as f:
        for r in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
            field, commodity = MEASURES.get(r["Harvest disposition"]), by_crop.get(r["Type of crop"])
            if field is None or commodity is None:
                continue                                   # another measure or crop: not read
            dguid = r["DGUID"]
            p = _PROVINCE.match(dguid)
            region = "" if _CANADA.match(dguid) else (province_map.get(p.group(1)) if p else None)
            if region is None:
                skip(f"an aggregate of provinces ({r['GEO']})")
                continue
            if r["STATUS"] in NOT_PUBLISHED or not r["VALUE"].strip():
                skip(f"not published ({NOT_PUBLISHED.get(r['STATUS'], 'no value')})")
                continue
            year = int(r["REF_DATE"])
            if year == ry and rm < 12:
                skip("season in progress — released before the November survey's final production")
                continue
            if r["UOM"] not in ("Hectares", "Metric tonnes", "Kilograms per hectare") or r["SCALAR_FACTOR"] != "units":
                raise FetchError(f"{commodity} {r['GEO']} {year}: unit '{r['UOM']}' scale '{r['SCALAR_FACTOR']}' "
                                 "is not the table's metric units — refused, never guessed")
            vals.setdefault((commodity, region, year), {})[field] = float(r["VALUE"])
    rows = []
    for (commodity, region, year), v in sorted(vals.items()):
        prod, area = v.get("prod"), v.get("area")
        if prod is None:
            if area is not None:
                skip("an area with no production figure")
            continue
        prev = vals.get((commodity, region, year - 1), {}).get("prod")
        rows.append({"commodity": commodity, "country": "CA", "region_code": region, "season_year": year,
                     "production_tonnes": store_round(prod, 1), "area_harvested_ha": store_round(area, 1),
                     "yield_tonnes_ha": store_round(v["yield"] / 1000, 4) if v.get("yield") is not None else None,
                     "yoy_change_pct": store_round((prod - prev) / prev * 100, 2) if prev else None,
                     "note": "Statistics Canada 32-10-0359-01, metric units as published; definition per the crop "
                             "registry's statcan_label"})
    return rows, dict(sorted(aside.items()))


def parse(data: bytes, province_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(province_map.items())))[0]


def set_aside(data: bytes, province_map: dict[str, str]) -> dict[str, int]:
    return _read(data, tuple(sorted(province_map.items())))[1]
