"""Company operational sites — a food/agri company's OWN footprint (HQ, plants, warehouses, DCs).

Give a company a LOCATED site and its physical risk becomes computable, from the same golden source
its suppliers run through. Mirrors services/reference/footprint.py (issuer HQ seeding) but org-scoped
for the agri workspace: geocode the address (or take coordinates), snap to the H3 res-8 grid, persist
an sc_company_sites row with provenance, and score that cell via the shared on-demand scorer
(services.scoring.on_demand.process_new_cells) — no second, drifting scoring path.

Honesty: if geocoding fails and no coordinates were given, we add NOTHING and say so — never a
fabricated location. A site in a cell the golden source hasn't reached yet comes back 'not yet scored'.
"""
from __future__ import annotations

import logging
from typing import Optional

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.geocoding.nominatim import geocode
from services.scoring.on_demand import schedule_scoring

logger = logging.getLogger(__name__)

H3_RESOLUTION = 8
SITE_TYPES = {"hq", "factory", "warehouse", "distribution_centre", "office", "other"}

# v0 business-interruption: expected annual downtime as a FRACTION of the year, by hazard band.
# Illustrative, uncalibrated — a transparent parametric (worse hazard → more expected downtime), to be
# replaced by a calibrated hazard→outage curve. BI exposure = annual throughput × this fraction.
BI_DOWNTIME_FLAG = "v0-illustrative"


def bi_downtime_fraction(score: float | None) -> float:
    if score is None:
        return 0.0
    if score >= 75:   # ~22 days/yr
        return 0.06
    if score >= 60:   # ~11 days/yr
        return 0.03
    if score >= 40:   # ~3.6 days/yr
        return 0.01
    return 0.0


class SiteLocationError(ValueError):
    """Raised when a site can be neither geocoded nor given coordinates — we refuse to invent one."""


def resolve_location(address: Optional[str], lat: Optional[float], lon: Optional[float],
                     session=None) -> dict:
    """Return {lat, lon, precision, confidence, low_confidence, resolved_name}. Coordinates win;
    else geocode the address (cache-aware when a session is supplied) with a real, provider-derived
    confidence/precision — no more a flat 0.6."""
    if lat is not None and lon is not None:
        return {"lat": float(lat), "lon": float(lon), "precision": "exact", "confidence": 1.0,
                "low_confidence": False, "resolved_name": None}
    if address and address.strip():
        if session is not None:
            from services.geocoding.geocoder import best
            hit = best(session, address.strip())
        else:
            hit = geocode(address.strip())
        if hit:
            return {"lat": hit["lat"], "lon": hit["lon"],
                    "precision": hit.get("precision", "geocoded"),
                    "confidence": hit.get("confidence", 0.6),
                    "low_confidence": hit.get("low_confidence", False),
                    "resolved_name": hit.get("display_name")}
    raise SiteLocationError("could not locate the site — provide coordinates or a geocodable address")


def add_site(session: Session, org_id: str, name: str, site_type: str = "other",
             address: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None,
             country: Optional[str] = None, region: Optional[str] = None,
             annual_value_eur: Optional[float] = None, annual_throughput_eur: Optional[float] = None,
             source: str = "user_entry") -> dict:
    """Locate → snap to H3 → persist → score. Returns the created site row (with its H3 cell)."""
    site_type = site_type if site_type in SITE_TYPES else "other"
    loc = resolve_location(address, lat, lon, session=session)
    cell = h3.latlng_to_cell(loc["lat"], loc["lon"], H3_RESOLUTION)

    row = session.execute(text("""
        INSERT INTO sc_company_sites
            (org_id, name, site_type, address, latitude, longitude, h3_cell, country, region,
             annual_value_eur, annual_throughput_eur, confidence, geocode_precision, source)
        VALUES (:org, :name, :type, :addr, :lat, :lon, :cell, :country, :region,
                :value, :throughput, :conf, :prec, :source)
        RETURNING site_id::text
    """), {"org": org_id, "name": name, "type": site_type, "addr": address,
           "lat": loc["lat"], "lon": loc["lon"], "cell": cell, "country": country, "region": region,
           "value": annual_value_eur, "throughput": annual_throughput_eur,
           "conf": loc["confidence"], "prec": loc["precision"], "source": source}).first()
    session.commit()

    # score the cell in the background if the golden source hasn't reached it — a fresh cell means
    # slow ERA5/raster reads, so we don't block the add (the site is already saved; score lands shortly)
    schedule_scoring({cell: (loc["lat"], loc["lon"])})

    return {"site_id": row[0], "name": name, "site_type": site_type, "lat": loc["lat"], "lon": loc["lon"],
            "h3_cell": cell, "geocode_precision": loc["precision"]}


def list_sites_with_risk(session: Session, org_id: str,
                         scenario: str = "baseline", horizon: str = "current") -> list[dict]:
    """Each site + its worst standing hazard on the given basis (for the operations table / map, and
    for E1). Basis defaults to present-state (baseline/current); when the caller reports at a projected
    scenario/horizon the site risk is read on THAT basis, so the number matches the label the filing
    carries (audit T3). A site with no projection at the requested horizon simply has no hazard there —
    same honest behaviour as the sourcing side, which is already basis-scoped."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (s.site_id)
               s.site_id::text, s.name, s.site_type, CAST(s.latitude AS FLOAT) lat, CAST(s.longitude AS FLOAT) lon,
               s.country, s.h3_cell, CAST(s.annual_value_eur AS FLOAT) value_eur,
               CAST(s.annual_throughput_eur AS FLOAT) throughput_eur,
               CAST(s.confidence AS FLOAT) confidence, s.geocode_precision,
               v.hazard_type AS top_hazard, CAST(v.physical_risk_score AS FLOAT) hazard_score
        FROM sc_company_sites s
        LEFT JOIN v_sc_site_physical_risk v
               ON v.site_id = s.site_id AND v.scenario = :sc AND v.time_horizon = :hz
        WHERE s.org_id = :o
        ORDER BY s.site_id, v.physical_risk_score DESC NULLS LAST
    """), {"o": org_id, "sc": scenario, "hz": horizon}).mappings().all()
    out = []
    for r in rows:
        d = dict(r)
        # business-interruption exposure = throughput × expected-downtime fraction (v0 illustrative)
        d["bi_at_risk_eur"] = round((d.get("throughput_eur") or 0) * bi_downtime_fraction(d.get("hazard_score")), 0) or None
        # input-quality flags (audit T4b): coarse geocode, or located-but-not-yet-scored (no euro possible)
        d["low_confidence"] = bool(d.get("lat") is not None and (
            (d.get("confidence") is not None and d["confidence"] < 0.5)
            or d.get("geocode_precision") in ("region", "country")))
        d["insufficient_data"] = bool(d.get("lat") is not None and d.get("hazard_score") is None)
        out.append(d)
    return out


def site_hazards(session: Session, site_id: str) -> list[dict]:
    """All standing hazards scored for one site (for the detail panel)."""
    rows = session.execute(text("""
        SELECT hazard_type, CAST(physical_risk_score AS FLOAT) AS score, scenario, time_horizon, model_version, scored_at
        FROM v_sc_site_physical_risk
        WHERE site_id = :id AND scenario = 'baseline' AND time_horizon = 'current'
        ORDER BY physical_risk_score DESC NULLS LAST
    """), {"id": site_id}).mappings().all()
    return [dict(r) for r in rows]
