"""Realized climate exposure — the real, named climate events that have ALREADY crossed a book.

Every climate-risk tool sells the future: "your 2050 risk under a warming scenario." Buyers find that
abstract and easy to defer. This is the opposite, and it is the platform's most distinctive asset: using the
OBSERVED event catalogs Tellumen already holds — 35k+ historical storm tracks (IBTrACS), 17k+ earthquakes
(USGS), and observed crop-yield shocks — it shows an institution the real events that have already passed
over its OWN assets. Not a model output: named storms, dated earthquakes, measured yield failures, matched by
location to the customer's book.

It reframes the entire conversation from "trust our projection" to "here is what already happened to you" —
grounded entirely in observed, authoritative data. Honest by construction: an event is listed only where a
real catalogued event actually falls within the stated distance of a real asset; distances and severities are
the catalogue's own; nothing is projected or fabricated.
"""
from __future__ import annotations

import math

from sqlalchemy import text
from sqlalchemy.orm import Session

_STORM_RADIUS_KM = 120.0     # tropical/extra-tropical wind field reaches well beyond the eye
_QUAKE_RADIUS_KM = 150.0     # felt/damaging radius for a significant quake
_MIN_MAGNITUDE = 5.0         # significant earthquakes only
_SSHS_LABEL = {5: "Cat 5", 4: "Cat 4", 3: "Cat 3", 2: "Cat 2", 1: "Cat 1", 0: "Tropical storm", -1: "Depression"}


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def events_near_point(session: Session, lat: float, lon: float,
                      storm_radius_km: float = _STORM_RADIUS_KM,
                      quake_radius_km: float = _QUAKE_RADIUS_KM,
                      min_magnitude: float = _MIN_MAGNITUDE) -> dict:
    """The observed storms and earthquakes that have crossed a single location — the point-level realized
    exposure behind the any-address Climate Track Record. Real catalogued events only."""
    m = max(storm_radius_km, quake_radius_km) / 111.0 + 0.5   # deg margin for the bbox pre-filter
    storm_pts = session.execute(text("""
        SELECT storm_id, storm_name, season_year, sshs_category, CAST(max_wind_kt AS FLOAT) AS wind,
               CAST(lat AS FLOAT) AS lat, CAST(lon AS FLOAT) AS lon
        FROM storm_events WHERE lat BETWEEN :a AND :b AND lon BETWEEN :c AND :d
    """), {"a": lat - m, "b": lat + m, "c": lon - m, "d": lon + m}).mappings().all()
    storms: dict = {}
    for pt in storm_pts:
        d = _haversine_km(lat, lon, pt["lat"], pt["lon"])
        if d <= storm_radius_km:
            sid = pt["storm_id"]
            st = storms.setdefault(sid, {"name": (pt["storm_name"] or "Unnamed").title(), "year": pt["season_year"],
                                         "category": -1, "wind": 0, "closest_km": d})
            st["category"] = max(st["category"], pt["sshs_category"] or -1)
            st["wind"] = max(st["wind"] or 0, pt["wind"] or 0)
            st["closest_km"] = min(st["closest_km"], d)
    storm_events = [{"kind": "storm", "name": st["name"], "year": st["year"],
                     "severity": _SSHS_LABEL.get(st["category"], "Storm"),
                     "max_wind_kt": round(st["wind"]) if st["wind"] else None,
                     "closest_km": round(st["closest_km"], 1)} for st in storms.values()]

    quakes = session.execute(text("""
        SELECT CAST(magnitude AS FLOAT) AS mag, region_name, origin_time,
               CAST(epicentre_lat AS FLOAT) AS lat, CAST(epicentre_lon AS FLOAT) AS lon
        FROM seismic_events WHERE CAST(magnitude AS FLOAT) >= :m
          AND epicentre_lat BETWEEN :a AND :b AND epicentre_lon BETWEEN :c AND :d
    """), {"m": min_magnitude, "a": lat - m, "b": lat + m, "c": lon - m, "d": lon + m}).mappings().all()
    quake_events = []
    for q in quakes:
        d = _haversine_km(lat, lon, q["lat"], q["lon"])
        if d <= quake_radius_km:
            quake_events.append({"kind": "earthquake", "name": f'M{q["mag"]:.1f} · {q["region_name"] or "—"}',
                                 "year": q["origin_time"].year if q["origin_time"] else None,
                                 "severity": f'Magnitude {q["mag"]:.1f}', "magnitude": q["mag"],
                                 "closest_km": round(d, 1)})
    events = sorted(storm_events + quake_events, key=lambda e: -(e["year"] or 0))
    return {"n_events": len(events), "n_storms": len(storm_events), "n_earthquakes": len(quake_events),
            "events": events}


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


def located_realized_exposure(session: Session, org_id: str, vertical: str,
                              storm_radius_km: float = _STORM_RADIUS_KM,
                              quake_radius_km: float = _QUAKE_RADIUS_KM,
                              min_magnitude: float = _MIN_MAGNITUDE) -> dict:
    """For a located book (bank / insurer / reit), the observed storms and earthquakes that crossed it."""
    assets = _located_assets(session, org_id, vertical)
    if not assets:
        return {"available": False, "reason": "no_located_assets"}
    by_id = {a["id"]: a for a in assets}
    la0, la1, lo0, lo1 = _bbox(assets, margin_deg=2.5)

    def _asset_rows(hit: dict) -> list[dict]:
        # the individual assets an event crossed — the drill-down behind n_assets, closest first
        rows = [{"id": aid, "name": by_id[aid]["name"], "value_eur": round(by_id[aid]["value"] or 0),
                 "closest_km": round(dist, 1)} for aid, dist in hit.items() if aid in by_id]
        return sorted(rows, key=lambda r: r["closest_km"])[:25]

    # ── Storms (IBTrACS tracks) — a storm affects an asset if any track point is within the wind-field radius.
    storm_pts = session.execute(text("""
        SELECT storm_id, storm_name, season_year, sshs_category, CAST(max_wind_kt AS FLOAT) AS wind,
               CAST(lat AS FLOAT) AS lat, CAST(lon AS FLOAT) AS lon
        FROM storm_events
        WHERE lat BETWEEN :a AND :b AND lon BETWEEN :c AND :d
    """), {"a": la0, "b": la1, "c": lo0, "d": lo1}).mappings().all()
    storms: dict = {}
    for pt in storm_pts:
        for a in assets:
            d = _haversine_km(a["lat"], a["lon"], pt["lat"], pt["lon"])
            if d <= storm_radius_km:
                sid = pt["storm_id"]
                st = storms.setdefault(sid, {
                    "name": (pt["storm_name"] or "Unnamed").title(), "year": pt["season_year"],
                    "category": max((pt["sshs_category"] or -1), -1), "max_wind_kt": pt["wind"] or 0,
                    "assets": {}, "closest_km": d})
                st["category"] = max(st["category"], pt["sshs_category"] or -1)
                st["max_wind_kt"] = max(st["max_wind_kt"] or 0, pt["wind"] or 0)
                st["closest_km"] = min(st["closest_km"], d)
                prev = st["assets"].get(a["id"])
                if prev is None or d < prev:
                    st["assets"][a["id"]] = d

    def _storm_out(sid, st):
        exposed = sum(a["value"] or 0 for a in assets if a["id"] in st["assets"])
        return {"kind": "storm", "name": st["name"], "year": st["year"],
                "severity": _SSHS_LABEL.get(st["category"], "Storm"),
                "max_wind_kt": round(st["max_wind_kt"]) if st["max_wind_kt"] else None,
                "n_assets": len(st["assets"]), "value_exposed_eur": round(exposed),
                "closest_km": round(st["closest_km"], 1), "assets": _asset_rows(st["assets"])}
    storm_events = [_storm_out(sid, st) for sid, st in storms.items()]

    # ── Earthquakes (USGS) — a significant quake affects an asset within the felt radius.
    quakes = session.execute(text("""
        SELECT event_id, CAST(magnitude AS FLOAT) AS mag, region_name, origin_time,
               CAST(epicentre_lat AS FLOAT) AS lat, CAST(epicentre_lon AS FLOAT) AS lon
        FROM seismic_events
        WHERE CAST(magnitude AS FLOAT) >= :m
          AND epicentre_lat BETWEEN :a AND :b AND epicentre_lon BETWEEN :c AND :d
    """), {"m": min_magnitude, "a": la0, "b": la1, "c": lo0, "d": lo1}).mappings().all()
    quake_events = []
    for q in quakes:
        hit = {}
        for a in assets:
            d = _haversine_km(a["lat"], a["lon"], q["lat"], q["lon"])
            if d <= quake_radius_km:
                hit[a["id"]] = d
        if hit:
            exposed = sum(a["value"] or 0 for a in assets if a["id"] in hit)
            quake_events.append({"kind": "earthquake", "name": f'M{q["mag"]:.1f} · {q["region_name"] or "—"}',
                                 "year": q["origin_time"].year if q["origin_time"] else None,
                                 "severity": f'Magnitude {q["mag"]:.1f}', "magnitude": q["mag"],
                                 "n_assets": len(hit), "value_exposed_eur": round(exposed),
                                 "closest_km": round(min(hit.values()), 1), "assets": _asset_rows(hit)})

    events = storm_events + quake_events
    if not events:
        return {"available": True, "n_events": 0, "n_assets": len(assets), "events": [],
                "note": "No catalogued storm or earthquake in the observed record falls within the felt radius "
                        "of this book's assets."}
    events.sort(key=lambda e: (-(e["year"] or 0), -(e["value_exposed_eur"] or 0)))
    years = [e["year"] for e in events if e["year"]]
    total_exposed = max((e["value_exposed_eur"] or 0) for e in events) if events else 0
    return {
        "available": True,
        "n_events": len(events),
        "n_storms": len(storm_events),
        "n_earthquakes": len(quake_events),
        "n_assets": len(assets),
        "since_year": min(years) if years else None,
        "peak_value_exposed_eur": round(total_exposed),
        "events": events[:20],
        "headline": f"{len(events)} real climate events have crossed this book"
                    + (f" since {min(years)}" if years else "") + " — observed, not modelled.",
        "method": ("Observed events from the storm (IBTrACS) and earthquake (USGS) catalogues, matched by "
                   f"distance to the book's own asset coordinates (storm wind-field ≤ {round(storm_radius_km)} km, "
                   f"quake felt-radius ≤ {round(quake_radius_km)} km, magnitude ≥ {min_magnitude}). Real catalogued "
                   "events only — nothing projected or fabricated."),
    }


def agri_realized_exposure(session: Session, org_id: str) -> dict:
    """For an agri sourcing book, the observed crop-yield shocks in the commodity × country the buyer sources."""
    sourced = session.execute(text("""
        SELECT co.name AS commodity, p.country AS country, SUM(CAST(p.annual_spend_eur AS FLOAT)) AS spend
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = CAST(:o AS uuid) GROUP BY co.name, p.country
    """), {"o": org_id}).mappings().all()
    if not sourced:
        return {"available": False, "reason": "no_sourcing_book"}
    spend_by = {(r["commodity"].lower(), (r["country"] or "").upper()): float(r["spend"] or 0) for r in sourced}

    shocks = session.execute(text("""
        SELECT commodity, country, season_year, CAST(yoy_change_pct AS FLOAT) AS yoy
        FROM crop_yield_observations
        WHERE yoy_change_pct < -5 ORDER BY season_year DESC
    """)).mappings().all()
    events = []
    for sh in shocks:
        key = (str(sh["commodity"]).lower(), str(sh["country"]).upper())
        spend = spend_by.get(key)
        if spend and spend > 0:
            events.append({"kind": "crop_shock", "commodity": sh["commodity"].title(), "country": sh["country"],
                           "year": sh["season_year"], "yoy_change_pct": round(sh["yoy"], 1),
                           "spend_eur": round(spend),
                           "severity": f'{round(sh["yoy"], 1)}% yield'})
    if not events:
        return {"available": True, "n_events": 0, "events": [],
                "note": "No observed yield shock on record for a commodity × origin this buyer sources."}
    events.sort(key=lambda e: (-(e["year"] or 0), e["yoy_change_pct"]))
    years = [e["year"] for e in events if e["year"]]
    return {
        "available": True, "n_events": len(events), "since_year": min(years) if years else None,
        "spend_exposed_eur": round(sum({(e["commodity"], e["country"]): e["spend_eur"] for e in events}.values())),
        "events": events[:20],
        "headline": f"{len(events)} real yield shocks have hit this buyer's sourcing origins"
                    + (f" since {min(years)}" if years else "") + " — observed, not modelled.",
        "method": ("Observed national crop-yield failures (year-on-year decline > 5%) from the agency yield "
                   "record, matched to the commodity × country this buyer actually sources. Real observed "
                   "shocks only."),
    }


def realized_exposure(session: Session, org_id: str, vertical: str) -> dict:
    """Router entry — dispatch to the located-book or agri realized-exposure ledger by sector."""
    if vertical in ("banking", "insurance", "realestate", "assetmgmt"):
        return located_realized_exposure(session, org_id, vertical)
    if vertical in ("agri", "supply", "manufacturer"):
        return agri_realized_exposure(session, org_id)
    return {"available": False, "reason": "unsupported_sector"}
