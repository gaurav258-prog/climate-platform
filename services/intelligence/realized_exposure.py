"""Realized exposure — the recorded storms, earthquakes and production shocks that have ALREADY crossed a book.

Every climate-risk tool sells the future: "your 2050 risk under a warming scenario." This is the opposite: using the
OBSERVED event catalogues the platform holds — the IBTrACS tropical-cyclone best tracks, the USGS earthquake catalogue
and the agencies' national crop-production records — it shows an institution the recorded events that have already passed over its
OWN assets. Not a model output: named storms, dated earthquakes, measured falls in production, matched by location to the
customer's book.

Facts only, by construction: an event is listed only where a catalogued event falls within the stated distance of a
real asset; the class, wind, magnitude and distance are the catalogue's own; nothing is projected. A crossing is not a
loss — the catalogues record where an event was, not what it damaged — and the words say so (message codes realized.*).
"""
from __future__ import annotations

import math

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages

# What counts as a crossing — the review's stated definition, returned with every result
# (data/reference/money/parameters.json lists the same three for the underwriting review).
_STORM_RADIUS_KM = 120.0     # a storm whose centre (a best-track point) passes within this distance of the asset
_QUAKE_RADIUS_KM = 150.0     # an earthquake whose epicentre lies within this distance
_MIN_MAGNITUDE = 5.0         # significant earthquakes only
_SHOCK_PCT = -5.0            # a production shock: national production fell by more than 5 % on the year before

# IBTrACS USA_SSHS: 1..5 Saffir-Simpson categories, 0 tropical storm, -1 tropical depression, -2 subtropical,
# -3 disturbance, -4 post-tropical, -5 unknown. Every class below a tropical storm ranks below it.
_TROPICAL_STORM = 0


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def storm_strength(category: int | None, wind_kt: float | None) -> tuple[int, float]:
    """How strong a best-track point is, for picking a storm's strongest point within reach: its Saffir-Simpson class
    (every class below a tropical storm counts as below it), then its wind. A tropical storm is class 0 — never
    read as 'no class' (E-next: `category or -1` made every tropical storm a depression)."""
    rank = category if category is not None and category >= _TROPICAL_STORM else _TROPICAL_STORM - 1
    return rank, float(wind_kt or 0.0)


def storm_class(category: int | None) -> str:
    """The class a storm's best track gives it, in words ('Category 3', 'Tropical storm', 'Post-tropical')."""
    return messages.name("realized.storm_class", str(-5 if category is None else int(category)))


def storm_name(raw: str | None) -> str:
    """A best-track name in words: 'LESLIE' → 'Leslie'; agencies' two names 'ANNETTE:JAMINY' → 'Annette / Jaminy'."""
    parts = [p.strip().title() for p in (raw or "").split(":") if p.strip()]
    return " / ".join(parts) if parts else messages.label("realized.storm.unnamed")


def definition() -> dict:
    """What counts as a crossing (the stated definition every result carries)."""
    return {"storm_radius_km": _STORM_RADIUS_KM, "quake_radius_km": _QUAKE_RADIUS_KM, "min_magnitude": _MIN_MAGNITUDE}


def _span(first, last) -> dict | None:
    if first is None or last is None:
        return None
    a, b = (first.date() if hasattr(first, "date") else first), (last.date() if hasattr(last, "date") else last)
    return {"first": a.isoformat(), "last": b.isoformat(), "years": round((b - a).days / 365.25, 1)}


def catalogue_spans(session: Session, min_magnitude: float = _MIN_MAGNITUDE) -> dict[str, dict | None]:
    """The years each observed catalogue covers, from its first record to its last — the window an observed frequency
    is counted over. A span in days, not calendar years: a catalogue from July 2016 to July 2026 covers 10.0 years, not
    11 (E-next)."""
    s = session.execute(text("SELECT MIN(observation_time), MAX(observation_time) FROM storm_events")).first()
    q = session.execute(text("SELECT MIN(origin_time), MAX(origin_time) FROM seismic_events "
                             "WHERE CAST(magnitude AS FLOAT) >= :m"), {"m": min_magnitude}).first()
    return {"storm": _span(*s) if s else None, "earthquake": _span(*q) if q else None}


def sources(spans: dict[str, dict | None]) -> list[dict]:
    """The catalogues behind a result, named in words, with the years they cover."""
    record = {"storm": "storm", "earthquake": "seismic"}
    return [{"kind": k, "name": messages.name("event_record", record[k]), **v} for k, v in spans.items() if v]


def _storm_points(session: Session, la0: float, la1: float, lo0: float, lo1: float):
    return session.execute(text("""
        SELECT storm_id, storm_name, season_year, sshs_category AS cat, CAST(max_wind_kt AS FLOAT) AS wind,
               observation_time AS at, CAST(lat AS FLOAT) AS lat, CAST(lon AS FLOAT) AS lon
        FROM storm_events
        WHERE lat BETWEEN CAST(:a AS numeric) AND CAST(:b AS numeric) AND lon BETWEEN CAST(:c AS numeric) AND CAST(:d AS numeric)
    """), {"a": la0, "b": la1, "c": lo0, "d": lo1}).mappings().all()


def _quakes(session: Session, la0: float, la1: float, lo0: float, lo1: float, min_magnitude: float):
    return session.execute(text("""
        SELECT event_id, CAST(magnitude AS FLOAT) AS mag, region_name, origin_time, CAST(depth_km AS FLOAT) AS depth,
               CAST(epicentre_lat AS FLOAT) AS lat, CAST(epicentre_lon AS FLOAT) AS lon
        FROM seismic_events
        WHERE CAST(magnitude AS FLOAT) >= :m
          AND epicentre_lat BETWEEN CAST(:a AS numeric) AND CAST(:b AS numeric) AND epicentre_lon BETWEEN CAST(:c AS numeric) AND CAST(:d AS numeric)
    """), {"m": min_magnitude, "a": la0, "b": la1, "c": lo0, "d": lo1}).mappings().all()


def _storm_event(st: dict) -> dict:
    """A storm that crossed: its strongest best-track point within reach (class, wind) and its closest approach."""
    best = st["best"]
    return {"kind": "storm", "id": st["id"], "name": storm_name(st["name"]), "year": st["year"],
            "date": st["closest_at"].date().isoformat() if st["closest_at"] else None,
            "category": best["cat"], "strength": storm_class(best["cat"]),
            "max_wind_kt": round(st["wind"]) if st["wind"] else None, "closest_km": round(st["closest_km"], 1)}


def _quake_event(q, closest_km: float) -> dict:
    return {"kind": "earthquake", "id": q["event_id"],
            "name": q["region_name"] or messages.label("realized.quake.unplaced"),
            "year": q["origin_time"].year if q["origin_time"] else None,
            "date": q["origin_time"].date().isoformat() if q["origin_time"] else None,
            "magnitude": round(q["mag"], 1), "strength": f'Magnitude {q["mag"]:.1f}',
            "depth_km": round(q["depth"], 1) if q["depth"] is not None else None, "closest_km": round(closest_km, 1)}


def _cross_storms(points, sites: list[dict], radius_km: float) -> dict:
    """{storm_id: {…, 'sites': {site_id: closest km}}} — every storm whose centre came within reach of a site."""
    storms: dict = {}
    for pt in points:
        for a in sites:
            d = _haversine_km(a["lat"], a["lon"], pt["lat"], pt["lon"])
            if d > radius_km:
                continue
            st = storms.setdefault(pt["storm_id"], {"id": pt["storm_id"], "name": pt["storm_name"], "year": pt["season_year"],
                                                    "best": pt, "wind": 0.0, "closest_km": d, "closest_at": pt["at"],
                                                    "sites": {}})
            if storm_strength(pt["cat"], pt["wind"]) > storm_strength(st["best"]["cat"], st["best"]["wind"]):
                st["best"] = pt
            st["wind"] = max(st["wind"], pt["wind"] or 0.0)
            if d < st["closest_km"]:
                st["closest_km"], st["closest_at"] = d, pt["at"]
            if d < st["sites"].get(a["id"], float("inf")):
                st["sites"][a["id"]] = d
    return storms


def events_near_point(session: Session, lat: float, lon: float,
                      storm_radius_km: float = _STORM_RADIUS_KM,
                      quake_radius_km: float = _QUAKE_RADIUS_KM,
                      min_magnitude: float = _MIN_MAGNITUDE) -> dict:
    """The observed storms and earthquakes that have crossed one location — behind the any-address track record and
    each policy of the underwriting review. Catalogued events only, latest first."""
    m = max(storm_radius_km, quake_radius_km) / 111.0 + 0.5   # degrees of margin for the box pre-filter
    site = [{"id": "here", "lat": lat, "lon": lon}]
    storms = _cross_storms(_storm_points(session, lat - m, lat + m, lon - m, lon + m), site, storm_radius_km)
    storm_events = [_storm_event(st) for st in storms.values()]
    quake_events = []
    for q in _quakes(session, lat - m, lat + m, lon - m, lon + m, min_magnitude):
        d = _haversine_km(lat, lon, q["lat"], q["lon"])
        if d <= quake_radius_km:
            quake_events.append(_quake_event(q, d))
    events = sorted(storm_events + quake_events, key=lambda e: (-(e["year"] or 0), e["closest_km"]))
    return {"n_events": len(events), "n_storms": len(storm_events), "n_earthquakes": len(quake_events), "events": events}


def _located_assets(session: Session, org_id: str, vertical: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT entity_id::text AS id, entity_name AS name, CAST(latitude AS FLOAT) AS lat,
               CAST(longitude AS FLOAT) AS lon, CAST(primary_value_eur AS FLOAT) AS value
        FROM portfolio_entities
        WHERE org_id = CAST(:o AS uuid) AND vertical = :v AND latitude IS NOT NULL AND longitude IS NOT NULL
    """), {"o": org_id, "v": vertical}).mappings().all()
    return [dict(r) for r in rows]


def _bbox(assets: list[dict], margin_deg: float):
    lats = [a["lat"] for a in assets]
    lons = [a["lon"] for a in assets]
    return min(lats) - margin_deg, max(lats) + margin_deg, min(lons) - margin_deg, max(lons) + margin_deg


def _params(storm_radius_km: float, quake_radius_km: float, min_magnitude: float) -> dict:
    return {"storm_km": round(storm_radius_km), "quake_km": round(quake_radius_km), "min_mag": f"{min_magnitude:g}"}


def located_realized_exposure(session: Session, org_id: str, vertical: str,
                              storm_radius_km: float = _STORM_RADIUS_KM,
                              quake_radius_km: float = _QUAKE_RADIUS_KM,
                              min_magnitude: float = _MIN_MAGNITUDE) -> dict:
    """For a located book (bank / insurer / real estate / asset manager), the observed storms and earthquakes that
    crossed it, each with the assets within reach and the value they hold."""
    assets = _located_assets(session, org_id, vertical)
    if not assets:
        return {"available": False, "message": messages.render("realized.unavailable.no_assets")}
    by_id = {a["id"]: a for a in assets}
    la0, la1, lo0, lo1 = _bbox(assets, margin_deg=2.5)
    p = _params(storm_radius_km, quake_radius_km, min_magnitude)

    def _crossed(hit: dict) -> dict:
        # the individual assets an event crossed — the drill-down behind n_assets, closest first
        rows = sorted(({"id": aid, "name": by_id[aid]["name"], "value_eur": round(by_id[aid]["value"] or 0),
                        "closest_km": round(dist, 1)} for aid, dist in hit.items()), key=lambda r: r["closest_km"])
        return {"n_assets": len(hit), "value_exposed_eur": round(sum(by_id[aid]["value"] or 0 for aid in hit)),
                "assets": rows[:25]}

    storms = _cross_storms(_storm_points(session, la0, la1, lo0, lo1), assets, storm_radius_km)
    storm_events = [{**_storm_event(st), **_crossed(st["sites"])} for st in storms.values()]
    crossed = {aid for st in storms.values() for aid in st["sites"]}
    quake_events = []
    for q in _quakes(session, la0, la1, lo0, lo1, min_magnitude):
        hit = {a["id"]: d for a in assets if (d := _haversine_km(a["lat"], a["lon"], q["lat"], q["lon"])) <= quake_radius_km}
        if hit:
            quake_events.append({**_quake_event(q, min(hit.values())), **_crossed(hit)})
            crossed |= set(hit)

    events = storm_events + quake_events
    src = sources(catalogue_spans(session, min_magnitude))
    if not events:
        return {"available": True, "n_events": 0, "n_assets": len(assets), "events": [], "sources": src,
                "definition": definition(), "message": messages.render("realized.book.none", **p)}
    events.sort(key=lambda e: (-(e["year"] or 0), -(e["value_exposed_eur"] or 0)))
    years = [e["year"] for e in events if e["year"]]
    return {
        "available": True,
        "n_events": len(events),
        "n_storms": len(storm_events),
        "n_earthquakes": len(quake_events),
        "n_assets": len(assets),
        "n_assets_crossed": len(crossed),
        "value_crossed_eur": round(sum(by_id[aid]["value"] or 0 for aid in crossed)),
        "since_year": min(years) if years else None,
        "peak_value_exposed_eur": max(e["value_exposed_eur"] or 0 for e in events),
        "events": events[:20],
        "sources": src,
        "definition": definition(),
        "message": messages.render("realized.book.crossed", **p),
    }


def agri_realized_exposure(session: Session, org_id: str) -> dict:
    """For an agri sourcing book, the observed falls in national production of the crops the buyer sources, in the
    countries it sources them from (crop_yield_observations.yoy_change_pct is the change in production, not in yield
    per hectare — E-next: it was shown as '% yield')."""
    sourced = session.execute(text("""
        SELECT co.name AS commodity, p.country AS country, SUM(CAST(p.annual_spend_eur AS FLOAT)) AS spend
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = CAST(:o AS uuid) GROUP BY co.name, p.country
    """), {"o": org_id}).mappings().all()
    if not sourced:
        return {"available": False, "message": messages.render("realized.unavailable.no_sourcing")}
    spend_by = {(r["commodity"].lower(), (r["country"] or "").upper()): float(r["spend"] or 0) for r in sourced}

    from ml.features.yield_series import shocks as observed_shocks
    shocks = observed_shocks(session, _SHOCK_PCT)       # one source per crop and country — never counted per source (E156)
    events = []
    for sh in shocks:
        key = (str(sh["commodity"]).lower(), str(sh["country"]).upper())
        spend = spend_by.get(key)
        if spend and spend > 0:
            events.append({"kind": "crop_shock", "commodity": sh["commodity"].title(), "country": sh["country"],
                           "year": sh["season_year"], "yoy_change_pct": round(sh["yoy"], 1),
                           "spend_eur": round(spend), "strength": f'{round(sh["yoy"], 1)} % production'})
    p = {"threshold": f"{-_SHOCK_PCT:g}"}
    if not events:
        return {"available": True, "n_events": 0, "events": [], "message": messages.render("realized.book.no_crops", **p)}
    events.sort(key=lambda e: (-(e["year"] or 0), e["yoy_change_pct"]))
    years = [e["year"] for e in events if e["year"]]
    return {
        "available": True, "n_events": len(events), "since_year": min(years) if years else None,
        "spend_exposed_eur": round(sum({(e["commodity"], e["country"]): e["spend_eur"] for e in events}.values())),
        "events": events[:20],
        "message": messages.render("realized.book.crops", **p),
    }


def realized_exposure(session: Session, org_id: str, vertical: str) -> dict:
    """Router entry — dispatch to the located-book or agri realized-exposure ledger by sector."""
    if vertical in ("banking", "insurance", "realestate", "assetmgmt"):
        return located_realized_exposure(session, org_id, vertical)
    if vertical in ("agri", "supply", "manufacturer"):
        return agri_realized_exposure(session, org_id)
    return {"available": False, "message": messages.render("realized.unavailable.sector")}

