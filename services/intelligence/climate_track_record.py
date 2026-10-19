"""Climate Track Record — a per-address dossier for transaction diligence.

The product line built on Realized Exposure. A bank lending against a property, an insurer taking on a risk or a fund
acquiring an asset asks of one location: *what has already happened here, and how does it score today?* This answers
both, for any coordinates, and keeps them apart:

  * the OBSERVED record — the storms and earthquakes in the observed catalogues that have crossed this location (see
    realized_exposure); facts, with the catalogue's own class, wind, magnitude and distance;
  * the MODELLED scores — the platform's current hazard scores for the grid cell, labelled as modelled. Only a scale
    that expresses the likelihood or intensity of damaging conditions may be the location's highest hazard
    (core/hazard_relevance.py); a nowcast reading, a crop scale, a susceptibility class or a variability rank is
    context (E245: the headline read 'acute heat 100/100', today's reading).

A diligence dossier, not a regulatory filing. Every explanation is a catalogue message (codes realized.place.*).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages
from core.hazard_relevance import INTENSITY, scale_kind
from core.types import score_to_bucket
from services.intelligence.realized_exposure import (
    _MIN_MAGNITUDE,
    _QUAKE_RADIUS_KM,
    _STORM_RADIUS_KM,
    catalogue_spans,
    definition,
    events_near_point,
    sources,
)


def _current_scores(session: Session, h3_cell: str) -> list[dict]:
    # the scores held today: one row per hazard at the baseline scenario and current horizon (DISTINCT ON guards against
    # a duplicate lane or version row), highest first; each with the kind of scale it is on
    rows = session.execute(text("""
        SELECT DISTINCT ON (hazard_type) hazard_type, CAST(risk_score AS FLOAT) AS score,
               model_version, data_vintage
        FROM canonical_scores
        WHERE h3_cell = :c AND valid_to IS NULL AND scenario = 'baseline' AND time_horizon = 'current'
        ORDER BY hazard_type, risk_score DESC
    """), {"c": h3_cell}).mappings().all()
    out = []
    for r in rows:
        scale = scale_kind(r["hazard_type"], r["model_version"])
        out.append({"hazard": r["hazard_type"], "label": messages.name("hazard", r["hazard_type"]),
                    "score": round(r["score"], 1), "bucket": score_to_bucket(r["score"]).value,
                    "scale": scale, "scale_name": messages.name("realized.scale", scale), "headline": scale == INTENSITY,
                    "model_version": r["model_version"],
                    "as_of": r["data_vintage"].date().isoformat() if r["data_vintage"] else None})
    out.sort(key=lambda h: (not h["headline"], -h["score"]))   # likelihood scales first, highest first
    return out


def track_record(session: Session, lat: float, lon: float, name: str | None = None,
                 h3_cell: str | None = None) -> dict:
    """The track record of one location: the observed events that have crossed it, and its modelled scores today."""
    if h3_cell is None:
        import h3
        h3_cell = h3.latlng_to_cell(lat, lon, 8)

    past = events_near_point(session, lat, lon)
    present = _current_scores(session, h3_cell)
    likelihood = [h for h in present if h["headline"]]
    years = [e["year"] for e in past["events"] if e["year"]]
    spans = catalogue_spans(session, _MIN_MAGNITUDE)
    p = {"storm_km": round(_STORM_RADIUS_KM), "quake_km": round(_QUAKE_RADIUS_KM), "min_mag": f"{_MIN_MAGNITUDE:g}",
         "storm_from": (spans["storm"] or {}).get("first", "")[:4], "quake_from": (spans["earthquake"] or {}).get("first", "")[:4]}

    return {
        "location": {"name": name, "lat": lat, "lon": lon, "h3_cell": h3_cell},
        "since_year": min(years) if years else None,
        "realized": {**past, "sources": sources(spans), "definition": definition(),
                     "message": messages.render("realized.place.crossed" if past["n_events"] else "realized.place.none", **p)},
        "current_risk": present,
        "headline_current": likelihood[0] if likelihood else None,
        "modelled": {"message": messages.render("realized.place.modelled" if present else "realized.place.unscored"),
                     "context": messages.render("realized.place.context")
                     if any(not h["headline"] for h in present) else None},
    }


def _wrap(s: str, width: int = 92) -> list[str]:
    out = []
    while s:
        cut = s if len(s) <= width else s[:width].rsplit(" ", 1)[0]
        out.append(cut)
        s = s[len(cut):].lstrip()
    return out


def track_record_pdf(session: Session, lat: float, lon: float, name: str | None = None) -> tuple[str, bytes]:
    """The track record as a one-page PDF a diligence team can hand over — the same words as the screen. Reuses the
    dependency-free PDF writer. Returns (filename, pdf_bytes)."""
    from services.governance.assurance_pack import _render_cover_pdf
    tr = track_record(session, lat, lon, name)
    loc = name or f"{lat:.4f}, {lon:.4f}"
    past, msg = tr["realized"], tr["realized"]["message"]
    lines: list[tuple[str, str]] = [(loc, "head"), (f"{lat:.5f}, {lon:.5f}", "normal"), ("", "normal"),
                                    (msg["label"], "head")]
    for e in past["events"][:12]:
        bits = [e["name"], str(e.get("year") or "—"), e["strength"]]
        if e.get("max_wind_kt"):
            bits.append(f"{e['max_wind_kt']} kt")
        lines.append(("- " + "  ·  ".join(bits) + f"  ·  {e['closest_km']} km", "mono"))
    lines += [(x, "normal") for part in ("what", "why") if msg["detail"].get(part) for x in _wrap(msg["detail"][part])]
    lines.append(("", "normal"))
    mod = tr["modelled"]["message"]
    lines.append((mod["label"], "head"))
    for h in [h for h in tr["current_risk"] if h["headline"]][:12]:
        lines.append((f"- {h['label']}: {h['score']:g} of 100", "mono"))
    lines += [(x, "normal") for x in _wrap(mod["detail"]["what"])]
    lines.append(("", "normal"))
    for s in past["sources"]:
        lines.append((f"{s['name']}: {s['first']} to {s['last']}", "normal"))
    blob = _render_cover_pdf("Climate Track Record", lines)
    safe = "".join(c if c.isalnum() else "-" for c in loc)[:40].strip("-") or "location"
    return f"climate-track-record-{safe}.pdf", blob
