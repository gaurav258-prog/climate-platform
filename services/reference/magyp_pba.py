"""Argentina's crop estimates for the province of Buenos Aires — a reviewed yield source: the national agriculture
secretariat's estimates (Dirección de Estimaciones Agrícolas) as the province republishes them by partido on its open
data portal (CC BY 4.0), summed here to one series per crop for the province (ISO 3166-2 AR-B, region reference).
The national files are not reachable from the platform (the secretariat's portal refuses it); this is the official
republication of the same estimates, for one province.

Read as published: 'produccion' (tonnes) and 'superficie_cosechada' (hectares) per partido and campaign, for every crop
of the registry that names its 'cultivo' (magyp_pba); the province's figure is the sum over its partidos (the
'Ignorado' line — district not stated — included); yield = production ÷ harvested area. A campaign ('2020/21') belongs
to the calendar year its crop's Buenos Aires season ends (the registry's harvest_year: 'first' for a season within one
calendar year — wheat, durum, barley — 'second' for one crossing the new year; it agrees with MIRCA-OS's calendar,
tests/unit/test_regional_calibration.py). The national series stays FAOSTAT's (national precedence).

What the reader sets aside, counted and shown with the release:
  * a value the publisher does not give ('SD', sin dato) or an empty one
  * an area with no production figure for the year
"""
from __future__ import annotations

import csv
import hashlib
import io
from functools import lru_cache

from services.reference import publisher_errors as P
from services.reference.yield_sources import SetAside, store_round

SOURCE = "MAGyP estimaciones (Provincia de Buenos Aires)"
BASE = ("https://catalogo.datos.gba.gob.ar/dataset/4ee50a8f-6866-4191-9bf8-aebb30b0d718/resource/"
        "d3e23031-164a-43e0-b104-01ced63e4abd/download/estimaciones-agricolas-1969_2026.csv")
REGION = "AR-B"
PARSER_VERSION = "magyp-pba-v1"
COLUMNS = ("cultivo", "campania", "municipio_id", "produccion", "superficie_cosechada")
_UA = {"User-Agent": "Tellumen reference refresh (+https://tellumen.io)"}

FetchError = P.PublisherError
PUBLISHER = "Provincia de Buenos Aires (datos abiertos)"


def crops() -> dict[str, tuple[str, str]]:
    """{the publisher's 'cultivo': (our commodity, 'first' | 'second' — the campaign year the harvest belongs to)}."""
    from ml.features.crop_registry import crops as registry
    return {c["magyp_pba"]["cultivo"]: (c["commodity"], c["magyp_pba"]["harvest_year"])
            for c in registry() if c.get("magyp_pba")}


def countries(session) -> dict[str, str]:
    """The province this file covers, by the region reference: {'06': 'AR-B'} (INDEC's province code)."""
    from services.reference import regions
    if REGION not in regions.of_country("AR"):
        raise FetchError("agri.feed.unexpected_member", source=PUBLISHER, crop="—", member=REGION,
                         where="the region reference")
    return {"06": REGION}


def reader(province_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    h.update(REGISTRY.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(province_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def published(last_modified: str | None, etag: str | None, timeout: int = 60) -> dict:
    """Ask the portal whether the file changed (HEAD): {changed, last_modified, etag}. No validators held → changed."""
    import requests
    try:
        r = requests.head(BASE, headers=_UA, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        raise P.unreachable(PUBLISHER, e) from e
    if r.status_code >= 400:
        raise P.answered(PUBLISHER, r.status_code, "the file check")
    lm, et = r.headers.get("Last-Modified"), r.headers.get("ETag")
    same = (et and et == etag) or (not et and lm and lm == last_modified)
    return {"changed": not same, "last_modified": lm, "etag": et}


def download(timeout: int = 300) -> bytes:
    import requests
    try:
        r = requests.get(BASE, headers=_UA, timeout=timeout)
    except requests.RequestException as e:
        raise P.unreachable(PUBLISHER, e) from e
    if r.status_code != 200 or not r.content:
        raise P.answered(PUBLISHER, r.status_code, "the download")
    return r.content


def _num(v: str) -> float | None:
    v = (v or "").strip()
    return float(v) if v and v.replace(".", "", 1).isdigit() else None


@lru_cache(maxsize=2)
def _read(data: bytes, provinces: tuple[tuple[str, str], ...]) -> tuple[list[dict], list[dict]]:
    by_crop, province_map = crops(), dict(provinces)
    aside = SetAside()
    reader_ = csv.DictReader(io.StringIO(data.decode("utf-8-sig")))
    missing = [c for c in COLUMNS if c not in (reader_.fieldnames or [])]
    if missing:
        raise FetchError("agri.feed.no_table", source=PUBLISHER)
    sums: dict[tuple[str, str, int], dict[str, float]] = {}
    for r in reader_:
        crop = by_crop.get(r["cultivo"])
        if crop is None:
            continue                                       # another crop: not read
        commodity, harvest = crop
        region = province_map.get(r["municipio_id"][:2])
        if region is None:
            raise FetchError("agri.feed.unexpected_member", source=PUBLISHER, crop=commodity,
                             member=f"district {r['municipio_id']}", where=r["campania"])
        start = int(r["campania"].split("/")[0])
        year = start if harvest == "first" else start + 1
        acc = sums.setdefault((commodity, region, year), {"prod": 0.0, "area": 0.0, "n_prod": 0, "n_area": 0})
        prod, area = _num(r["produccion"]), _num(r["superficie_cosechada"])
        if prod is None:
            aside.add("not_published", why="no data (SD)" if r["produccion"].strip() == "SD" else "no value")
        else:
            acc["prod"] += prod
            acc["n_prod"] += 1
        if area is not None:
            acc["area"] += area
            acc["n_area"] += 1
    out = []
    for (commodity, region, year), v in sorted(sums.items()):
        if not v["n_prod"]:
            if v["n_area"]:
                aside.add("area_only")
            continue
        prod, area = v["prod"], v["area"] if v["n_area"] else None
        prev = sums.get((commodity, region, year - 1), {})
        prev_prod = prev.get("prod") if prev.get("n_prod") else None
        out.append({"commodity": commodity, "country": "AR", "region_code": region, "season_year": year,
                    "production_tonnes": store_round(prod, 1), "area_harvested_ha": store_round(area, 1),
                    "yield_tonnes_ha": store_round(prod / area, 4) if area else None,
                    "yoy_change_pct": store_round((prod - prev_prod) / prev_prod * 100, 2) if prev_prod else None,
                    "note": "the national agriculture secretariat's estimates as the province of Buenos Aires publishes "
                            "them by district, summed to the province (tonnes, hectares); campaign assigned to the year "
                            "its season ends"})
    return out, aside.counts()


def parse(data: bytes, province_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(province_map.items())))[0]


def set_aside(data: bytes, province_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(province_map.items())))[1]
