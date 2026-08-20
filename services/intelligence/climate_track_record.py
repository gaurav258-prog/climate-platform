"""Climate Track Record — a portable, per-address climate-risk dossier for transaction diligence.

The product line built on top of Realized Exposure. A bank underwriting a loan, an insurer taking on a risk,
or a fund acquiring an asset asks one question about a specific property or counterparty: *what is this
location's climate track record?* This answers it in one artifact, for any address on Earth, fusing the two
things Tellumen uniquely holds together:

  * the PAST — the real, named climate events (storms, earthquakes) that have already crossed this exact
    location, from the observed catalogues (see realized_exposure); and
  * the PRESENT/FUTURE — the platform's current hazard scores for the location.

It is a diligence deliverable, not a regulatory filing — a different buyer and a different budget. Honest by
construction: the past is observed catalogue events only; the present is the golden-source score with its
vintage, and where a hazard is not yet scored it says so rather than inventing a number.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.types import score_to_bucket
from services.intelligence.realized_exposure import events_near_point

_HAZARD_LABEL = {
    "flood": "Flood", "coastal_flood": "Coastal flood", "storm": "Storm", "wildfire": "Wildfire",
    "seismic": "Earthquake", "volcanic": "Volcanic", "heat_chronic": "Chronic heat", "heat_acute": "Acute heat",
    "drought": "Drought", "soil_water": "Soil-water stress", "pollution": "Pollution",
}


def _current_scores(session: Session, h3_cell: str) -> list[dict]:
    # the present nowcast: one row per hazard at baseline scenario / current horizon (DISTINCT ON guards
    # against any duplicate lane/version rows), highest score first.
    rows = session.execute(text("""
        SELECT DISTINCT ON (hazard_type) hazard_type, CAST(risk_score AS FLOAT) AS score,
               model_version, data_vintage
        FROM canonical_scores
        WHERE h3_cell = :c AND valid_to IS NULL AND scenario = 'baseline' AND time_horizon = 'current'
        ORDER BY hazard_type, risk_score DESC
    """), {"c": h3_cell}).mappings().all()
    out = []
    for r in rows:
        out.append({"hazard": r["hazard_type"], "label": _HAZARD_LABEL.get(r["hazard_type"], r["hazard_type"].title()),
                    "score": round(r["score"], 1), "bucket": score_to_bucket(r["score"]).value,
                    "model_version": r["model_version"], "data_vintage": str(r["data_vintage"]) if r["data_vintage"] else None})
    out.sort(key=lambda h: -h["score"])   # headline (highest current score) first
    return out


def track_record(session: Session, lat: float, lon: float, name: str | None = None,
                 h3_cell: str | None = None) -> dict:
    """The climate track record for a single location: observed events that have already crossed it +
    the current hazard scores + a plain-language verdict."""
    if h3_cell is None:
        import h3
        h3_cell = h3.latlng_to_cell(lat, lon, 8)

    past = events_near_point(session, lat, lon)
    present = _current_scores(session, h3_cell)
    headline_now = present[0] if present else None

    years = [e["year"] for e in past["events"] if e["year"]]
    verdict_bits = []
    if past["n_events"]:
        plural = past["n_events"] != 1
        verdict_bits.append(f"{past['n_events']} real climate event{'s' if plural else ''} "
                            + ("have" if plural else "has") + " already crossed this location"
                            + (f" since {min(years)}" if years else ""))
    else:
        verdict_bits.append("No catalogued storm or earthquake on record has crossed this location")
    if headline_now:
        verdict_bits.append(f"its biggest current physical threat is {headline_now['label'].lower()} "
                            f"({headline_now['bucket']} · {headline_now['score']}/100)")

    return {
        "location": {"name": name, "lat": lat, "lon": lon, "h3_cell": h3_cell},
        "verdict": " — ".join(verdict_bits) + ".",
        "realized": past,
        "current_risk": present,
        "headline_current": headline_now,
        "since_year": min(years) if years else None,
        "note": ("Diligence dossier — the PAST is observed catalogue events (IBTrACS storms + USGS "
                 "earthquakes) within the felt radius of this exact location; the PRESENT is Tellumen's "
                 "current golden-source hazard scores (with model version + data vintage). A hazard not yet "
                 "scored for this cell is omitted, never invented. This is a risk dossier, not a filing."),
    }
