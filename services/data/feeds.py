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
#
# `maturity` names the actual state of the ingestion path, honestly — the registry must describe what
# LANDS, not what we aspire to:
#   live        — a real adapter lands rows to a queryable store
#   on_demand   — fetched live per-query from the source (not persisted to our store)
#   proxy       — a real feed, but standing in for a different source (named in `note`)
#   partial     — real but limited coverage (named in `note`)
#   estimated   — derived (e.g. sector-average), not a measured feed
#   planned     — adapter is stub / not yet in production
# `name` is the source we ACTUALLY ingest; any gap between that and the ideal source is stated in `note`.
FEEDS: list[dict] = [
    {"key": "climate_reanalysis", "name": "Copernicus / ECMWF — ERA5-Land", "category": "hazard",
     "cadence_days": 30, "invalidates_basis": True, "maturity": "live",
     "note": "European climate reanalysis — heat / drought / frost / soil-water / wind."},
    {"key": "flood", "name": "ERA5-Land runoff (flood proxy)", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True, "maturity": "proxy",
     "note": "GloFAS was withdrawn from the CDS in 2025; we currently proxy flood from ERA5-Land total "
             "runoff (source_provider='era5_total_runoff'). River-gauge/DEM terrain not yet landed."},
    {"key": "fire_thermal", "name": "NASA FIRMS (VIIRS active fire)", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True, "maturity": "live",
     "note": "Active fire real; Sentinel-3 SLSTR land-surface-temperature integration is stubbed, not in production."},
    {"key": "atmosphere", "name": "Copernicus CAMS", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False, "maturity": "on_demand",
     "note": "Air quality / dust / fire emissions, fetched per-query (not landed). Informs the risk view; "
             "E2 pollution is out of filing scope."},
    {"key": "imagery", "name": "Sentinel-1/2 (SAR + optical)", "category": "hazard",
     "cadence_days": 6, "invalidates_basis": True, "maturity": "planned",
     "note": "SAR backscatter and Sentinel-2 NDVI adapters are stub-only; not yet producing production rows."},
    {"key": "storms_ocean", "name": "NOAA IBTrACS (cyclone tracks)", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True, "maturity": "live",
     "note": "Tropical-cyclone tracks real (→ storm_events); Copernicus Marine sea-state not yet landed."},
    {"key": "geophysical", "name": "EMSC seismic (EU) · Smithsonian GVP", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False, "maturity": "partial",
     "note": "GVP volcanic real (→ volcanic_events); seismic is EMSC (Europe bbox only) with an ESHM20 "
             "zone-approximation fallback — global USGS/GEM not yet wired. Geophysical, not climate-attributable."},
    {"key": "deforestation", "name": "Hansen Global Forest Change", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "on_demand",
     "note": "Annual forest-loss, read at EUDR determination time (not landed); re-run determinations on each release."},
    {"key": "reference_lei", "name": "GLEIF (LEI)", "category": "reference",
     "cadence_days": 7, "invalidates_basis": False, "maturity": "live",
     "note": "Legal-entity identifiers; changes rename entities, not risk scores."},
    {"key": "reference_assets", "name": "Sector-intensity estimates (NACE)", "category": "reference",
     "cadence_days": 90, "invalidates_basis": False, "maturity": "estimated",
     "note": "Emissions are sector-average intensity × revenue (source='estimated'), NOT a Climate TRACE / GEM "
             "facility feed — no such client is wired. Labelled estimated throughout."},
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


def overdue_basis_feeds(session: Session) -> list[dict]:
    """Feeds that (a) drive an un-frozen filing (`invalidates_basis`) AND (b) are overdue for refresh.
    The pre-filing control: surface these so the operator refreshes the golden source BEFORE a stale
    figure can reach a filing — rather than only catching it after the fact (audit T4, staleness layer)."""
    return [{"key": f["key"], "name": f["name"], "days_since": f["days_since"], "cadence_days": f["cadence_days"]}
            for f in feed_freshness(session)
            if f["invalidates_basis"] and f["status"] == "overdue"]


def basis_freshness_at(session: Session) -> dict:
    """A compact freshness snapshot of the basis-driving feeds, to stamp into a frozen filing so an
    auditor can see how current the golden source was at freeze time."""
    return {f["key"]: f["status"] for f in feed_freshness(session) if f["invalidates_basis"]}


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
