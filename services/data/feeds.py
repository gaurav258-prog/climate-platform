"""Golden-source feed registry + freshness — is the data under a filing current?

A filing is only as current as the feeds beneath it. Each source refreshes on its own clock; a compliance
officer needs to see, at a glance, when each was last refreshed and whether it's due. This is the tracking
layer: the registry (what feeds exist, how often they should refresh, and whether a refresh invalidates a
live/un-frozen basis) plus freshness computed against the append-only `feed_refresh_log`.

The actual data pulls stay where they belong — scheduled ingestion jobs, external. Recording a refresh here
stamps the log (and can trigger a re-score); it does not itself fetch data. Honest about the boundary.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

# Registry — data positioning stays "direct from Europe's & America's satellites & agencies", never "free".
# `invalidates_basis` = a refresh of this feed changes live scores that feed an un-frozen ESRS / EUDR
# filing (so a re-score, and possibly a re-freeze, must follow). Feeds that inform the *risk view* but are
# NOT in the climate/nature filing scope are False: atmosphere (E2 pollution is out of scope) and
# geophysical (seismic/volcanic are not climate-attributable and not part of CSRD/EUDR).
FEEDS: list[dict] = [
    {"key": "climate_reanalysis", "name": "Copernicus / ECMWF (ERA5, SPEI)", "category": "hazard",
     "cadence_days": 30, "invalidates_basis": True,
     "note": "European climate reanalysis — heat / drought / frost / soil-water / wind."},
    {"key": "flood", "name": "Copernicus GloFAS + terrain", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True,
     "note": "Global flood awareness + river/terrain — flood and water-stress scoring."},
    {"key": "fire_thermal", "name": "NASA FIRMS · Sentinel-3 SLSTR", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True,
     "note": "Active fire (VIIRS/MODIS) + land-surface temperature — wildfire / acute heat."},
    {"key": "atmosphere", "name": "Copernicus CAMS", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False,
     "note": "Air quality, dust and fire emissions — informs the risk view; E2 pollution is out of filing scope."},
    {"key": "imagery", "name": "ESA Sentinel-1 SAR · Sentinel-2", "category": "hazard",
     "cadence_days": 6, "invalidates_basis": True,
     "note": "Radar + optical (10 m) — vegetation / NDVI, soil, change detection."},
    {"key": "storms_ocean", "name": "NOAA IBTrACS · Copernicus Marine", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True,
     "note": "Tropical-cyclone tracks + sea state — storm and coastal scoring."},
    {"key": "geophysical", "name": "USGS seismic · Smithsonian GVP · GEM", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False,
     "note": "Seismic & volcanic catalogs — geophysical (natural-catastrophe) risk, not climate-attributable."},
    {"key": "deforestation", "name": "Hansen Global Forest Change", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True,
     "note": "Annual forest-loss release; re-run EUDR determinations on each release."},
    {"key": "reference_lei", "name": "GLEIF (LEI)", "category": "reference",
     "cadence_days": 7, "invalidates_basis": False,
     "note": "Legal-entity identifiers; changes rename entities, not risk scores."},
    {"key": "reference_assets", "name": "Climate TRACE · Global Energy Monitor", "category": "reference",
     "cadence_days": 90, "invalidates_basis": False,
     "note": "Facility-level emissions and power/industrial asset reference."},
]
_BY_KEY = {f["key"]: f for f in FEEDS}


def _status(days_since: float | None, cadence: int) -> str:
    if days_since is None:
        return "untracked"          # no refresh recorded yet — honest, not alarming
    if days_since > cadence:
        return "overdue"
    if days_since > cadence * 0.8:
        return "due_soon"
    return "fresh"


def feed_freshness(session: Session) -> list[dict]:
    """Each registered feed + last refresh (from the log) + a fresh/due/overdue status."""
    rows = session.execute(text("""
        SELECT feed_key, MAX(created_at) last_refresh
        FROM feed_refresh_log GROUP BY feed_key
    """)).mappings().all()
    last = {r["feed_key"]: r["last_refresh"] for r in rows}
    now = datetime.now(timezone.utc)
    out = []
    for f in FEEDS:
        lr = last.get(f["key"])
        days = (now - lr).total_seconds() / 86400 if lr else None
        out.append({**f, "last_refresh": lr.isoformat() if lr else None,
                    "days_since": round(days, 1) if days is not None else None,
                    "status": _status(days, f["cadence_days"])})
    return out


def record_refresh(session: Session, feed_key: str, actor_user_id: str | None, note: str | None = None) -> dict:
    """Append a refresh event to the log (does NOT fetch data — the scheduled job does that)."""
    if feed_key not in _BY_KEY:
        raise ValueError(f"unknown feed '{feed_key}'")
    row = session.execute(text("""
        INSERT INTO feed_refresh_log (feed_key, status, note, actor_user_id)
        VALUES (:k, 'refreshed', :n, :u) RETURNING refresh_id, created_at
    """), {"k": feed_key, "n": note, "u": actor_user_id}).mappings().first()
    session.commit()
    return {"feed_key": feed_key, "refresh_id": str(row["refresh_id"]),
            "created_at": row["created_at"].isoformat(),
            "invalidates_basis": _BY_KEY[feed_key]["invalidates_basis"]}
