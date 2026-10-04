"""USDA NASS Quick Stats — a reviewed yield source holding the US national series and one series per state (E157).

Read for every crop of the registry that states its NASS series (data/reference/crop_registry.json: nass_production,
nass_area — the exact Quick Stats short_desc, nothing matched loosely) from the SURVEY program, annual, TOTAL domain,
reference period 'YEAR'. Levels: NATIONAL (region '') and STATE (ISO 3166-2, 'US-IA'), a state taken only when it is in
the region reference (services.reference.regions) — NASS's 'OTHER STATES' bucket is not a state.

What the reader sets aside, and the release shows (counted by reason):
  * a value NASS does not give as a number ('(D)' withheld, '(Z)', '(NA)' …)
  * a 'YEAR' figure NASS loaded together with an identical forecast of the same year ('YEAR - SEP FORECAST' …): for a
    season in progress Quick Stats repeats its latest forecast under 'YEAR' — it is that forecast, not an estimate,
    and is read once NASS publishes its estimate
  * an area for a year with no production estimate read (the June Acreage figure of a season in progress, or a
    production withheld) — a year is read where NASS gives its production estimate

Units are converted only by data/reference/nass_quickstats.json (USDA's standard weights); an unknown unit, or a bushel
of a crop without a stated bushel weight, is refused. Yield is production ÷ area (arithmetic on the two figures read).

The key (settings.NASS_API_KEY) must go in the query string (Quick Stats takes no header) — so no URL, request or
exception text that carries it is ever logged or raised: errors are rebuilt without the request and the key is blanked.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import requests

from services.reference.yield_sources import store_round

REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "nass_quickstats.json"
SOURCE = "USDA NASS Quick Stats"
BASE = "https://quickstats.nass.usda.gov/api"
PARSER_VERSION = "usda-nass-quickstats-v1"
_FILTER = [("source_desc", "SURVEY"), ("freq_desc", "ANNUAL"), ("domain_desc", "TOTAL"),
           ("agg_level_desc", "NATIONAL"), ("agg_level_desc", "STATE")]
_PERIODS = {"year": ("reference_period_desc", "YEAR"), "forecast": ("reference_period_desc__LIKE", "FORECAST")}


class FetchError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


def crops() -> dict[str, tuple[str, str]]:
    """{NASS short_desc: (our commodity, 'prod' | 'area')} from the crop registry."""
    from ml.features.crop_registry import crops as registry
    out = {}
    for c in registry():
        if c.get("nass_production"):
            out[c["nass_production"]] = (c["commodity"], "prod")
            out[c["nass_area"]] = (c["commodity"], "area")
    return out


def countries(session) -> dict[str, str]:
    """{NASS location: our code} — 'US' for the national figure, every US state of the region reference by its USPS
    code (Quick Stats' state_alpha) → its ISO 3166-2 code."""
    from services.reference import regions
    return {"US": "US", **{code.split("-", 1)[1]: code for code in regions.of_country("US")}}


def reader(location_map: dict[str, str]) -> str:
    from ml.features.crop_registry import REF as REGISTRY
    h = hashlib.sha256(PARSER_VERSION.encode())
    for p in (REF, REGISTRY):
        h.update(p.read_bytes())
    h.update(",".join(f"{k}:{v}" for k, v in sorted(location_map.items())).encode())
    return f"{PARSER_VERSION}:{h.hexdigest()[:16]}"


def _get(endpoint: str, params: list[tuple[str, str]]) -> dict:
    from core.config import settings
    key = settings.NASS_API_KEY
    if not key:
        raise FetchError("NASS_API_KEY is not set — the Quick Stats key goes in the environment (.env)")
    try:
        r = requests.get(f"{BASE}/{endpoint}/", params=[("key", key), ("format", "JSON"), *params],
                         headers={"User-Agent": "Tellumen reference refresh"}, timeout=180)
    except requests.RequestException as e:
        # the exception text carries the URL, and the URL carries the key: rebuilt, never chained
        raise FetchError(f"USDA NASS could not be reached ({type(e).__name__})") from None
    if r.status_code != 200:
        body = r.text[:200].replace(key, "<key>")
        raise FetchError(f"USDA NASS answered {r.status_code} on {endpoint}: {body}")
    return r.json()


def _count(params: list[tuple[str, str]]) -> int:
    return int(_get("get_counts", params)["count"])


def published(last_modified: str | None, etag: str | None) -> dict:
    """Has NASS loaded any record of the registry's series since the last release's stamp (its own load_time)? One
    count — no download. With no earlier stamp, nothing cheaper exists: changed."""
    if not last_modified:
        return {"changed": True, "last_modified": None, "etag": None}
    n = _count([*[("short_desc", d) for d in sorted(crops())], *_FILTER, ("load_time__GT", last_modified)])
    return {"changed": n > 0, "last_modified": last_modified, "etag": None}


def stamp(data: bytes) -> str | None:
    """A release's stamp is NASS's own: the latest load_time among the records downloaded."""
    times = [r["load_time"] for part in json.loads(data)["data"].values() for r in part]
    return max(times) if times else None


def download() -> bytes:
    """Every registry series × ('YEAR', forecasts) at national and state level, NASS's records as answered, in a fixed
    order. A query is counted first: Quick Stats answers an empty result with the same error as a malformed query, so
    'no records' is known from the count, and any error on a query that has records is a real failure."""
    out: dict = {}
    for desc in sorted(crops()):
        for kind, period in _PERIODS.items():
            q = [("short_desc", desc), period, *_FILTER]
            rows = _get("api_GET", q)["data"] if _count(q) else []
            out[f"{desc}|{kind}"] = sorted(rows, key=lambda r: (r["agg_level_desc"], r["state_alpha"], r["year"],
                                                               r["reference_period_desc"], r["load_time"]))
    return json.dumps({"data": out}, sort_keys=True, separators=(",", ":")).encode()


def _number(v: str) -> float | None:
    s = v.strip().replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None                                       # '(D)', '(Z)', '(NA)' … — not a number


@lru_cache(maxsize=2)
def _read(data: bytes, locations: tuple[tuple[str, str], ...]) -> tuple[list[dict], dict[str, int]]:
    """(rows, {reason: rows set aside}) — read once per file and location map (parse and set_aside share it)."""
    ref, by_desc, location_map = reference(), crops(), dict(locations)
    parts = json.loads(data)["data"]
    forecasts = {(r["short_desc"], r["agg_level_desc"], r["state_alpha"], int(r["year"]), r["load_time"], r["Value"])
                 for k, rows in parts.items() if k.endswith("|forecast") for r in rows}
    aside: dict[str, int] = {}
    vals: dict = {}
    for key, rows in parts.items():
        desc, kind = key.rsplit("|", 1)
        if kind != "year" or desc not in by_desc:
            continue
        commodity, field = by_desc[desc]
        for r in rows:
            loc = "US" if r["agg_level_desc"] == "NATIONAL" else r["state_alpha"]
            code = location_map.get(loc)
            v, year = _number(r["Value"]), int(r["year"])
            why = (f"not a state of the region reference ({r['location_desc']})" if code is None
                   else f"not given as a number ({r['Value'].strip()})" if v is None
                   else "season in progress — 'YEAR' repeats NASS's forecast"
                   if (desc, r["agg_level_desc"], r["state_alpha"], year, r["load_time"], r["Value"]) in forecasts
                   else None)
            if why:
                aside[why] = aside.get(why, 0) + 1
                continue
            vals.setdefault((commodity, code, year), {})[field] = v * _factor(ref, commodity, field, r["unit_desc"])
    rows = []
    for (commodity, code, year), v in sorted(vals.items()):
        prod, area = v.get("prod"), v.get("area")
        if prod is None:                # an area with no production estimate (June Acreage for a season in progress,
            why = "area without a production estimate for the year"     # or the production withheld): not a year read
            aside[why] = aside.get(why, 0) + 1
            continue
        prev = vals.get((commodity, code, year - 1), {}).get("prod")
        rows.append({"commodity": commodity, "country": "US", "region_code": "" if code == "US" else code,
                     "season_year": year,
                     "production_tonnes": store_round(prod, 1), "area_harvested_ha": store_round(area, 1),
                     "yield_tonnes_ha": store_round(prod / area, 4) if area else None,
                     "yoy_change_pct": store_round((prod - prev) / prev * 100, 2) if prev else None,
                     "note": "USDA NASS Quick Stats SURVEY, annual 'YEAR'; definition per the crop registry's nass_label; "
                             "yield = production ÷ area"})
    return rows, dict(sorted(aside.items()))


def _factor(ref: dict, commodity: str, field: str, unit: str) -> float:
    u = ref["units"].get(unit)
    if u is None or u["field"] != field:
        raise FetchError(f"{commodity}: NASS unit '{unit}' for {field} is not in data/reference/nass_quickstats.json — "
                         "refused, never guessed")
    if u.get("per_crop"):
        lb = ref["bushel_lb"].get(commodity)
        if lb is None:
            raise FetchError(f"{commodity}: no bushel weight stated in data/reference/nass_quickstats.json — refused")
        return lb * ref["lb_to_t"]
    return u["factor"]


def parse(data: bytes, location_map: dict[str, str]) -> list[dict]:
    return _read(data, tuple(sorted(location_map.items())))[0]


def set_aside(data: bytes, location_map: dict[str, str]) -> dict[str, int]:
    return _read(data, tuple(sorted(location_map.items())))[1]
