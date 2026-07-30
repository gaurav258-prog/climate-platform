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
FEEDS: list[dict] = [
    {"key": "climate_eu", "name": "Copernicus / ECMWF (ERA5, SPEI)", "category": "hazard",
     "cadence_days": 30, "invalidates_basis": True,
     "note": "European climate reanalysis driving heat / drought / soil-water scores."},
    {"key": "climate_us", "name": "NASA / USGS (FIRMS, terrain)", "category": "hazard",
     "cadence_days": 30, "invalidates_basis": True,
     "note": "US agency feeds for active-fire and terrain inputs."},
    {"key": "deforestation", "name": "Hansen Global Forest Change", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True,
     "note": "Annual forest-loss release; re-run EUDR determinations on each release."},
    {"key": "reference_lei", "name": "GLEIF (LEI)", "category": "reference",
     "cadence_days": 7, "invalidates_basis": False,
     "note": "Legal-entity identifiers; changes rename entities, not risk scores."},
    {"key": "reference_emissions", "name": "Climate TRACE", "category": "reference",
     "cadence_days": 90, "invalidates_basis": False,
     "note": "Facility-level emissions reference."},
    {"key": "reference_power", "name": "Global Energy Monitor (GEM)", "category": "reference",
     "cadence_days": 180, "invalidates_basis": False,
     "note": "Power & industrial asset reference."},
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
