"""The one reader of the crop-yield store (crop_yield_observations) for product code (E156).

The store holds several sources (FAOSTAT, Eurostat, USDA FAS, curated and sub-national series) whose definitions and
year conventions differ. Read naively — every row of a country — a consumer counts one event once per source (the
same Spanish olive collapse from FAOSTAT and from Eurostat) or averages milled rice with paddy rice. So every product
read goes through here, and the rule is one:

  * a series is never spliced from two sources: for a crop and country a consumer reads ONE source — the one it names,
    or the first in data/reference/yield_series.json 'national_precedence' that holds a national series
  * national figures are region_code = ''; a regional series is read only when its source (and region) is named
  * a source 'never_in_history' (USDA FAS: market years, other definitions) is never chosen by precedence
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "yield_series.json"
_FIELDS = {"production_tonnes", "yield_tonnes_ha", "area_harvested_ha", "yoy_change_pct"}


class SeriesError(ValueError):
    pass


@lru_cache(maxsize=1)
def rules() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


def precedence() -> list[str]:
    return list(rules()["national_precedence"])


def _field(field: str) -> str:
    if field not in _FIELDS:
        raise SeriesError(f"field must be one of {sorted(_FIELDS)}")
    return field


def series(session: Session, commodity: str, country: str, source: str, region_code: str | None = '',
           field: str = "production_tonnes") -> dict[int, float]:
    """{year: value} of ONE series. region_code '' = national; a code = that region; None = the source's only series
    for this crop and country (refused when it holds several — a choice is never made silently)."""
    f = _field(field)
    if region_code is None:
        regions = session.execute(text("""SELECT DISTINCT region_code FROM crop_yield_observations
                                          WHERE commodity = :c AND country = :o AND source = :s"""),
                                  {"c": commodity, "o": country, "s": source}).scalars().all()
        if len(regions) > 1:
            raise SeriesError(f"{source} holds {len(regions)} series of {commodity} in {country} ({sorted(regions)}) — "
                              "name the region")
        region_code = regions[0] if regions else ''
    rows = session.execute(text(f"""
        SELECT season_year, CAST({f} AS FLOAT) FROM crop_yield_observations
        WHERE commodity = :c AND country = :o AND source = :s AND region_code = :r AND {f} IS NOT NULL
        ORDER BY season_year"""), {"c": commodity, "o": country, "s": source, "r": region_code}).all()
    return {int(y): float(v) for y, v in rows}


def national_source(session: Session, commodity: str, country: str) -> str | None:
    """The source a consumer reads for this crop and country by the stated precedence (None: no national series)."""
    held = set(session.execute(text("""SELECT DISTINCT source FROM crop_yield_observations
                                       WHERE commodity = :c AND country = :o AND region_code = ''"""),
                               {"c": commodity, "o": country}).scalars())
    return next((s for s in precedence() if s in held), None)


def national(session: Session, commodity: str, country: str, source: str | None = None,
             field: str = "production_tonnes") -> tuple[str | None, dict[int, float]]:
    """(source used, {year: value}) — the named source, else the first by precedence."""
    src = source or national_source(session, commodity, country)
    return (src, series(session, commodity, country, src, '', field)) if src else (None, {})


def by_country(session: Session, commodity: str, source: str, field: str = "production_tonnes") -> dict[str, dict[int, float]]:
    """{country: {year: value}} — every NATIONAL series of one source for a crop (incl. 'WLD' where the source has it)."""
    f = _field(field)
    out: dict[str, dict[int, float]] = {}
    for country, year, v in session.execute(text(f"""
            SELECT country, season_year, CAST({f} AS FLOAT) FROM crop_yield_observations
            WHERE commodity = :c AND source = :s AND region_code = '' AND {f} IS NOT NULL"""),
            {"c": commodity, "s": source}).all():
        out.setdefault(country, {})[int(year)] = float(v)
    return out


def every_series(session: Session, commodity: str, country: str) -> dict[str, dict[int, float]]:
    """{'<source>' or '<source> · <region>': {year: production}} — every series held for a crop and country, kept
    apart (for audits that must find which series reproduces a stored calibration)."""
    out: dict[str, dict[int, float]] = {}
    for source, region, year, v in session.execute(text("""
            SELECT source, region_code, season_year, CAST(production_tonnes AS FLOAT) FROM crop_yield_observations
            WHERE commodity = :c AND country = :o AND production_tonnes IS NOT NULL ORDER BY season_year"""),
            {"c": commodity, "o": country}).all():
        out.setdefault(f"{source} · {region}" if region else source, {})[int(year)] = float(v)
    return out


def shocks(session: Session, below_pct: float, countries: list[str] | None = None) -> list[dict]:
    """Observed national year-on-year production falls below below_pct — for each crop and country from ONE source
    (by precedence), so an event is never counted once per source. [{commodity, country, season_year, yoy, source}]"""
    rows = session.execute(text("""
        SELECT commodity, country, season_year, CAST(yoy_change_pct AS FLOAT) AS yoy, source FROM crop_yield_observations
        WHERE region_code = '' AND yoy_change_pct < :t AND (CAST(:cc AS text[]) IS NULL OR country = ANY(CAST(:cc AS text[])))
        ORDER BY season_year DESC"""), {"t": below_pct, "cc": countries}).mappings().all()
    chosen: dict[tuple[str, str], str | None] = {}
    out = []
    for r in rows:
        key = (r["commodity"], r["country"])
        if key not in chosen:
            chosen[key] = national_source(session, *key)
        if r["source"] == chosen[key]:
            out.append(dict(r))
    return out


def mean_yield(session: Session, commodity: str, countries: list[str]) -> dict[int, float]:
    """{year: mean yield (t/ha) across the countries} — each country's yield from ITS one source by precedence."""
    per_year: dict[int, list[float]] = {}
    for c in countries:
        _, ys = national(session, commodity, c, field="yield_tonnes_ha")
        for y, v in ys.items():
            per_year.setdefault(y, []).append(v)
    return {y: sum(v) / len(v) for y, v in sorted(per_year.items())}


def latest(session: Session, commodity: str, source: str, country: str) -> dict:
    """{last: latest year, loaded: when it was loaded} of one national series."""
    r = session.execute(text("""SELECT max(season_year) AS last, max(ingested_at) AS loaded FROM crop_yield_observations
                                WHERE commodity = :c AND source = :s AND country = :o AND region_code = ''
                                  AND production_tonnes IS NOT NULL"""),
                        {"c": commodity, "s": source, "o": country}).mappings().first()
    return dict(r) if r else {"last": None, "loaded": None}
