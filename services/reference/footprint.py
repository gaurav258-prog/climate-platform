"""Footprint seeding — give a resolved issuer a LOCATED facility so its physical
risk becomes computable, from open data.

GLEIF gives an issuer's registered/headquarters ADDRESS but no coordinates. This
module geocodes that address (Nominatim/OSM, free) to a point, snaps it to the
platform's H3 res-8 grid, records it as an `issuer_facilities` row with full
provenance, and scores that cell against the golden source the same way an
any-address lookup does (services.scoring.on_demand.process_new_cells) — so
there is no second, drifting scoring path.

Honesty & scope, stated plainly:
  * This is a HQ PROXY footprint: one point, confidence 0.5, facility_type='hq'.
    It is the floor, not the truth — a manufacturer's real climate exposure is
    its plants, not its head office. Multi-facility footprints (Climate TRACE /
    Global Energy Monitor / OSM) are the next reference source; when they land,
    these HQ seeds are demoted by materiality weight, not deleted.
  * If geocoding fails, we return None and seed NOTHING — the issuer is honestly
    'no footprint yet', never a fabricated location.
  * Weight is 1.0 only because it is currently the sole known facility; the
    engine normalises per issuer, so adding real facilities re-balances it.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.geocoding.nominatim import geocode
from services.reference.gleif import GleifRecord

logger = logging.getLogger(__name__)

H3_RESOLUTION = 8  # matches canonical_scores
# A HQ is a proxy for the footprint, not the footprint itself — and the LESS
# precise the address we could match, the lower the confidence. Street-level is
# the best; a city-level fallback is coarser but valid (climate hazard is
# regional, so the right city is enough); country-level is a last resort.
CONF_STREET, CONF_CITY, CONF_COUNTRY = 0.5, 0.35, 0.15


def _hq_candidates(rec: GleifRecord) -> list[tuple[str, float, str]]:
    """Ordered address queries, most precise first, each with its confidence and
    a precision label. GLEIF addresses are often noisy (department names,
    building labels, region CODES like 'FR-IDF' the geocoder can't read), so we
    fall back from street → city → country rather than fail on the noise."""
    city = (rec.hq_city or "").strip()
    country = (rec.hq_country or rec.country or "").strip()
    cands: list[tuple[str, float, str]] = []
    # Street-level: first address line only (extra lines are usually noise) + city + country.
    if rec.hq_address_lines and city and country:
        cands.append((f"{rec.hq_address_lines[0]}, {city}, {country}", CONF_STREET, "street"))
    # City-level: almost always geocodes, and good enough for regional hazard.
    if city and country:
        cands.append((f"{city}, {country}", CONF_CITY, "city"))
    # Country-level: last resort, flagged very low confidence.
    if country:
        cands.append((country, CONF_COUNTRY, "country"))
    return cands


def issuer_has_facility(session: Session, issuer_id: str) -> bool:
    return bool(
        session.execute(
            text("SELECT 1 FROM issuer_facilities WHERE issuer_id = :i LIMIT 1"),
            {"i": issuer_id},
        ).first()
    )


def seed_hq_footprint(
    session: Session,
    issuer_id: str,
    rec: GleifRecord,
    *,
    score_cell: bool = True,
) -> Optional[dict]:
    """Geocode the issuer's HQ, record it as a facility with provenance, and
    (best-effort) score its cell. Returns the facility summary, or None if the
    address could not be geocoded (an honest 'no footprint', not a guess)."""
    candidates = _hq_candidates(rec)
    if not candidates:
        logger.info("issuer %s: no HQ address in GLEIF record — no footprint seeded", rec.lei)
        return None

    # Walk the ladder: take the first (most precise) query that geocodes.
    geo = confidence = precision = None
    for query, conf, label in candidates:
        try:
            hit = geocode(query)
        except Exception as exc:  # Nominatim down / rate-limited — surface, don't fabricate
            logger.warning("geocode failed for %s (%s): %s", rec.lei, query, exc)
            continue
        if hit:
            geo, confidence, precision = hit, conf, label
            break
    if not geo:
        logger.info("issuer %s: HQ address could not be geocoded at any precision", rec.lei)
        return None

    lat, lon = geo["lat"], geo["lon"]
    cell = h3.latlng_to_cell(lat, lon, H3_RESOLUTION)

    row = session.execute(
        text(
            """
            INSERT INTO issuer_facilities
                (issuer_id, name, facility_type, latitude, longitude, h3_cell,
                 country, region, materiality_weight, weight_basis,
                 source, source_ref, data_vintage, confidence)
            VALUES
                (:issuer_id, :name, 'hq', :lat, :lon, :cell,
                 :country, :region, 1.0, 'equal',
                 'osm', :source_ref, :vintage, :confidence)
            RETURNING facility_id
            """
        ),
        {
            "issuer_id": issuer_id,
            "name": "Registered headquarters" if precision == "street" else f"Registered headquarters ({precision}-level)",
            "lat": lat, "lon": lon, "cell": cell,
            "country": rec.hq_country or rec.country, "region": rec.hq_region,
            "source_ref": (geo.get("display_name") or "")[:160],
            "vintage": date.today(), "confidence": confidence,
        },
    ).mappings().one()
    facility_id = str(row["facility_id"])

    scoring = None
    if score_cell:
        # Score this cell against the golden source exactly like an any-address
        # lookup — sync hazards land immediately, gridded ones queue (Celery).
        try:
            from services.scoring.on_demand import process_new_cells
            scoring = process_new_cells({cell: (lat, lon)})
        except Exception as exc:
            logger.warning("on-demand scoring for %s cell %s failed: %s", rec.lei, cell, exc)

    return {
        "facility_id": facility_id, "h3_cell": cell,
        "latitude": lat, "longitude": lon,
        "facility_type": "hq", "confidence": confidence, "precision": precision,
        "source": "osm", "address": geo.get("display_name"),
        "scoring": scoring,
    }
