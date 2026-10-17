"""A reference data release as the operator's screen reads it (UI standard, product owner 2026-10-16): the release's
facts with every explanation as a code of the message catalogue (core/messages.py, reference.release.*) rendered in
customer words — the source's name and description, why rows were set aside, the notice that our reading changed,
the calibrations to re-check by crop, place and driver, and places by name, never by code.

The stored release is the review record and is never rewritten. Releases staged before set-aside reasons were codes
hold them as the reader's words; those are read to the same codes here (_LEGACY), so every release reads alike.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages
from services.governance.platform_policy import SYSTEM_USER
from services.reference import crop_releases as R
from services.reference import regions
from services.reference.yield_sources import SetAside, YieldSource, all_sources, by_label

# The readers' set-aside words before 2026-10-17 → the code (SetAside) and the value it carried.
_LEGACY: list[tuple[re.Pattern, str, Optional[str]]] = [(re.compile(p), c, v) for p, c, v in (
    (r"area without a production estimate for the year|an area with no production figure", "area_only", None),
    (r"not given as a number \((.*)\)", "not_a_number", "value"),
    (r"not published \((.*)\)", "not_published", "why"),
    (r"not a state of the region reference \((.*)\)", "state_group", "name"),
    (r"an aggregate of provinces \((.*)\)", "province_group", "name"),
    (r"NASS's combined counties \(.*\), not a county", "combined_counties", None),
    (r"not a county of the Census Bureau's 2020 county list \(.*\)", "not_a_county", None),
    (r"season in progress — 'YEAR' repeats NASS's forecast", "season_forecast", None),
    (r"season in progress — released before the November survey's final production", "season_preliminary", None),
    (r"a national or aggregate figure \(.*\)", "national_figure", None),
    (r"a NUTS-1 figure \(.*\)", "larger_region", None),
    (r"extra-regio \(not a territory\)", "extra_regio", None),
    (r"not a NUTS 2021 region \(.*\)", "other_nuts_version", None),
    (r"a summed crop with a part not published for the region and year", "part_unpublished", None),
)]


def _legacy(reason: str) -> tuple[Optional[str], dict]:
    for pattern, code, value in _LEGACY:
        m = pattern.fullmatch(reason)
        if m:
            return SetAside.PREFIX + code, ({value: m.group(1)} if value else {})
    return None, {}


def set_aside(stored) -> list[dict]:
    """The rows the reading set aside, largest first: [{code, label, detail, rows}]."""
    items = stored if isinstance(stored, list) else [
        {"code": c, "params": p, "rows": n, "words": why} for why, n in (stored or {}).items() for c, p in [_legacy(why)]]
    out = []
    for a in items:
        if a["code"]:
            m = messages.render(a["code"], **a["params"])
            out.append({"code": a["code"], "label": m["label"], "detail": m["detail"], "rows": a["rows"]})
        else:                                     # a reason no reader writes: shown as recorded
            out.append({"code": None, "label": a["words"], "detail": None, "rows": a["rows"]})
    return sorted(out, key=lambda a: -a["rows"])


class Places:
    """Countries and regions by name: the country reference (ref_countries) and the official region lists
    (services.reference.regions); a region with no name in its list keeps its official code."""

    def __init__(self, session: Session):
        self.countries = {r[0].strip(): r[1] for r in session.execute(text("SELECT iso2, name_en FROM ref_countries"))}

    def country(self, iso2: str) -> str:
        return self.countries.get(iso2, iso2)

    def __call__(self, country: str, region: str = "") -> str:
        if not region:
            return self.country(country)
        if region.count("-") == 2:                                       # a US county: 'US-IA-19001'
            state = region.rsplit("-", 1)[0]
            return f"{regions.counties(country).get(region) or region}, {regions.of_country(country).get(state, state)}"
        name = regions.of_country(country).get(region) or regions.nuts().get(region) or region
        return f"{name}, {self.country(country)}"


def driver(key: str) -> dict:
    """What a calibration reads the crop against, by name — the code's label and its detail."""
    m = messages.render(f"reference.release.driver.{key}")
    return {"label": m["label"], "detail": m["detail"]}


def source(ys: YieldSource) -> dict:
    m = messages.render(f"reference.release.source.{ys.key}")
    return {"name": m["label"], "about": m["detail"]}


def release(r: dict, places: Places) -> dict:
    """One release with its explanations rendered; its stored facts (file, reading, counts) kept for the record."""
    s = dict(r["summary"] or {})
    ys = by_label(r["source"])
    s["set_aside"] = set_aside(s.get("set_aside"))
    s["largest_revisions"] = [{**v, "place": places(v["country"], v.get("region_code") or "")}
                              for v in s.get("largest_revisions") or []]
    s["calibrations_may_be_affected"] = [{**f, "place": places.country(f["origin"]), "driver": driver(f["hazard_driver"])}
                                         for f in s.get("calibrations_may_be_affected") or []]
    return {**r, "summary": s, "source_key": ys.key if ys else None,
            "source_name": R.source_name(r["source"]),
            "reading_changed": messages.render("reference.release.reading_changed")
            if s.get("reader_changed_since_last_landed") else None,
            "proposed_by_name": messages.label("reference.release.by_platform")
            if r.get("proposed_by_id") == SYSTEM_USER else r.get("proposed_by")}


def releases(session: Session, limit: int = 20) -> list[dict]:
    places = Places(session)
    return [release(r, places) for r in R.releases(session, limit=limit)]


def rows(session: Session, release_id: str, change: Optional[str]) -> list[dict]:
    places = Places(session)
    return [{**x, "place": places(x["country"], x["region_code"] or "")} for x in R.release_rows(session, release_id, change)]


def feeds(session: Session) -> list[dict]:
    """Each reviewed source with its customer name and description, its schedule and where its last check stands."""
    from services.data.feeds import feed_freshness
    fresh = {f["key"]: f for f in feed_freshness(session)}
    return [{"source": ys.key, **source(ys),
             **{k: fresh[ys.feed_key].get(k) for k in ("cadence_days", "last_refresh", "last_status", "status",
                                                       "awaiting_review", "attribution")}}
            for ys in all_sources()]
