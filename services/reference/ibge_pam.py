"""IBGE Produção Agrícola Municipal (SIDRA tables 1612 and 1613) — a reviewed yield source holding one series per
Brazilian state for every crop of the registry that names its IBGE product (ibge_pam: the table and its product code,
with the product's name as IBGE publishes it, checked on every reading).

Read as published: 'Quantidade produzida' (variable 214, tonnes) and 'Área colhida' (variable 216, hectares) per state
(territorial level 3, the IBGE federative-unit code → ISO 3166-2 'BR-' + sigla, region reference); yield = production ÷
harvested area. The national series stays FAOSTAT's (national precedence) — this source is regional only.

What the reader sets aside, counted and shown with the release:
  * a year before the product's current basis (the registry's from_year — coffee is surveyed green-bean from 2002)
  * a value IBGE does not give as a number ('-' zero or none, '...' not available, 'X' suppressed)
  * an area with no production figure for the year
A unit other than tonnes and hectares, or a product name other than the registry's, is refused — never guessed.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from services.reference import publisher_errors as P
from services.reference.yield_sources import SetAside, store_round

SOURCE = "IBGE PAM (SIDRA 1612/1613)"
BASE = "https://apisidra.ibge.gov.br/values"
PARSER_VERSION = "ibge-pam-v1"
CLASSIFICATION = {"1612": "c81", "1613": "c82"}          # temporary and permanent crops
VARIABLES = {"214": ("prod", "Toneladas"), "216": ("area", "Hectares")}
NOT_PUBLISHED = {"-": "zero or none", "...": "not available", "X": "suppressed (confidentiality)", "..": "not applicable"}
_UA = {"User-Agent": "Tellumen reference refresh (+https://tellumen.io)"}

FetchError = P.PublisherError
PUBLISHER = "IBGE (SIDRA)"


def crops() -> dict[tuple[str, str], tuple[str, str, int | None]]:
    """{(table, product code): (our commodity, IBGE's product name, first year on the current basis or None)} from the
    crop registry."""
    from ml.features.crop_registry import crops as registry
    return {(c["ibge_pam"]["table"], c["ibge_pam"]["product"]):
            (c["commodity"], c["ibge_pam"]["label"], c["ibge_pam"].get("from_year"))
            for c in registry() if c.get("ibge_pam")}


def countries(session) -> dict[str, str]:
    """{IBGE federative-unit code: ISO 3166-2 code} — the region reference's IBGE list."""
    from services.reference import regions
    raw = json.loads((regions.DIR / regions.provenance()["files"]["BR"]["file"]).read_text(encoding="utf-8"))
    return {str(r["id"]): f"BR-{r['sigla']}" for r in raw}


def reader(uf_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    h.update(REGISTRY.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(uf_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def url(table: str, product: str) -> str:
    return f"{BASE}/t/{table}/n3/all/v/{','.join(VARIABLES)}/p/all/{CLASSIFICATION[table]}/{product}"


def published(last_modified: str | None, etag: str | None, timeout: int = 60) -> dict:
    """SIDRA states no validators for a query: the check reports a change, and the release's comparison with the store
    shows whether anything differs."""
    return {"changed": True, "last_modified": None, "etag": None}


def download(timeout: int = 300) -> bytes:
    """Every registry crop's state series, one SIDRA query each, kept together as one release: {"<table>/<product>":
    [rows as SIDRA returns them]} (the header row first)."""
    import requests
    out = {}
    for (table, product) in sorted(crops()):
        try:
            r = requests.get(url(table, product), headers=_UA, timeout=timeout)
        except requests.RequestException as e:
            raise P.unreachable(PUBLISHER, e) from e
        if r.status_code != 200 or not r.content:
            raise P.answered(PUBLISHER, r.status_code, "the download")
        out[f"{table}/{product}"] = r.json()
    return json.dumps(out, ensure_ascii=False, sort_keys=True).encode("utf-8")


@lru_cache(maxsize=2)
def _read(data: bytes, ufs: tuple[tuple[str, str], ...]) -> tuple[list[dict], list[dict]]:
    uf_map, by_product = dict(ufs), crops()
    aside = SetAside()
    vals: dict = {}
    for key, rows in sorted(json.loads(data).items()):
        table, product = key.split("/")
        if (table, product) not in by_product:
            continue                                        # a product the registry no longer names: not read
        commodity, label, from_year = by_product[(table, product)]
        for r in rows[1:]:
            if r["D4C"] != product or r["D4N"] != label:
                raise FetchError("agri.feed.unexpected_member", source=PUBLISHER, crop=commodity,
                                 member=f"product {r['D4C']} '{r['D4N']}'", where=f"table {table}")
            field, unit = VARIABLES.get(r["D2C"], (None, None))
            if field is None:
                continue
            if from_year and int(r["D3C"]) < from_year:
                aside.add("before_basis", year=str(from_year))     # another measure under the same code
                continue
            if r["V"] in NOT_PUBLISHED or not r["V"].strip():
                aside.add("not_published", why=NOT_PUBLISHED.get(r["V"], "no value"))
                continue
            if r["MN"] != unit:
                raise FetchError("agri.feed.unknown_unit", source=PUBLISHER, crop=commodity,
                                 unit=r["MN"], where=f"{r['D1N']} {r['D3C']}")
            region = uf_map.get(r["D1C"])
            if region is None:
                raise FetchError("agri.feed.unexpected_member", source=PUBLISHER, crop=commodity,
                                 member=f"federative unit {r['D1C']}", where=r["D1N"])
            vals.setdefault((commodity, region, int(r["D3C"])), {})[field] = float(r["V"])
    out = []
    for (commodity, region, year), v in sorted(vals.items()):
        prod, area = v.get("prod"), v.get("area")
        if prod is None:
            if area is not None:
                aside.add("area_only")
            continue
        prev = vals.get((commodity, region, year - 1), {}).get("prod")
        out.append({"commodity": commodity, "country": "BR", "region_code": region, "season_year": year,
                    "production_tonnes": store_round(prod, 1), "area_harvested_ha": store_round(area, 1),
                    "yield_tonnes_ha": store_round(prod / area, 4) if area else None,
                    "yoy_change_pct": store_round((prod - prev) / prev * 100, 2) if prev else None,
                    "note": "IBGE Produção Agrícola Municipal, state figures as published (tonnes, hectares); the crop "
                            "as the crop registry names its IBGE product"})
    return out, aside.counts()


def parse(data: bytes, uf_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(uf_map.items())))[0]


def set_aside(data: bytes, uf_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(uf_map.items())))[1]
