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
    {"key": "climate_reanalysis", "name": "Copernicus / ECMWF — ERA5 / ERA5-Land", "category": "hazard",
     "cadence_days": 30, "invalidates_basis": True, "maturity": "live",
     "note": "GLOBAL climate reanalysis — heat / drought / frost / soil-water / wind. Global baselines built "
             "(climatology_baseline temp+precip, soil_moisture_baseline, frost_baseline) so scoring is worldwide."},
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
    {"key": "geophysical", "name": "USGS seismic (global) · Smithsonian GVP", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False, "maturity": "partial",
     "note": "Seismic scores from the GLOBAL USGS M>=5.0 catalog (seismic_events, worldwide) + physics; the "
             "EMSC/ESHM20 European raster is a secondary background layer, not the scoring path. GVP volcanic "
             "real (→ volcanic_events) but hazard zones are curated per-volcano (no global fallback yet). "
             "Geophysical, not climate-attributable → out of CSRD/EUDR filing scope."},
    {"key": "deforestation", "name": "Hansen Global Forest Change", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "on_demand",
     "note": "Annual forest-loss, read at EUDR determination time (not landed); re-run determinations on each release."},
    {"key": "natura2000", "name": "EEA Natura 2000 (protected areas)", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "partial",
     "note": "EU protected-area boundaries, precomputed to an H3 lookup; flags own sites / sourcing plots in or "
             "near a Natura 2000 area (ESRS E4). One annual EEA release; EU coverage (WDPA global is the roadmap)."},
    {"key": "reference_lei", "name": "GLEIF (LEI)", "category": "reference",
     "cadence_days": 7, "invalidates_basis": False, "maturity": "live",
     "note": "Legal-entity identifiers; changes rename entities, not risk scores."},
    {"key": "reference_assets", "name": "Sector-intensity estimates (NACE)", "category": "reference",
     "cadence_days": 90, "invalidates_basis": False, "maturity": "estimated",
     "note": "Emissions are sector-average intensity × revenue (source='estimated'), NOT a Climate TRACE / GEM "
             "facility feed — no such client is wired. Labelled estimated throughout."},
]
_BY_KEY = {f["key"]: f for f in FEEDS}

# A feed is on the AUTOMATED scheduler when it has a landed ingestion path (live/proxy/partial). on_demand
# feeds refresh per-query, `planned` ones aren't wired, and `estimated` coefficients aren't a live feed —
# those are NOT auto-scheduled, and the monitor says so honestly rather than pretending they self-refresh.
_AUTO_MATURITY = {"live", "proxy", "partial"}
for _f in FEEDS:
    _f["auto_refresh"] = _f["maturity"] in _AUTO_MATURITY


# Which source feed(s) a hazard's score is derived from. canonical_scores carries no feed FK — the link is
# by construction (a hazard is scored from these feeds), so this registry IS the score→source provenance a
# lineage trace needs. Kept honest: a hazard maps only to feeds that genuinely drive it. Ordered primary-first.
HAZARD_FEEDS: dict[str, list[str]] = {
    "flood":         ["flood", "climate_reanalysis"],       # ERA5-Land runoff proxy + reanalysis
    "coastal_flood": ["climate_reanalysis"],                # ERA5 surge context + AR6 SLR (model, not a feed)
    "heat_acute":    ["climate_reanalysis"],
    "heat_chronic":  ["climate_reanalysis"],
    "drought":       ["climate_reanalysis"],                # ERA5-Land SPEI/soil-moisture
    "soil_water":    ["climate_reanalysis"],
    "frost":         ["climate_reanalysis"],                # ERA5 min-temperature
    "wildfire":      ["fire_thermal", "climate_reanalysis"],# NASA FIRMS + fire-weather
    "storm":         ["storms_ocean", "climate_reanalysis"],# IBTrACS + reanalysis
    "seismic":       ["geophysical"],                       # USGS
    "volcanic":      ["geophysical"],                       # Smithsonian GVP
    "pollution":     ["atmosphere"],                        # Copernicus CAMS
}


def feeds_for_hazard(session: Session, hazard: str) -> list[dict]:
    """The source feed(s) behind a hazard's score, each with live freshness — the score→source hop of a
    data-lineage trace. Empty if the hazard isn't mapped (never invents a source)."""
    keys = HAZARD_FEEDS.get(hazard, [])
    if not keys:
        return []
    fresh = {f["key"]: f for f in feed_freshness(session)}
    return [{"key": k, "name": fresh.get(k, {}).get("name", k),
             "maturity": fresh.get(k, {}).get("maturity"),
             "status": fresh.get(k, {}).get("status"),
             "last_refresh": fresh.get(k, {}).get("last_refresh")}
            for k in keys if k in fresh]


def _status(days_since: float | None, cadence: int) -> str:
    if days_since is None:
        return "untracked"          # no refresh recorded yet — honest, not alarming
    if days_since > cadence:
        return "overdue"
    if days_since > cadence * 0.8:
        return "due_soon"
    return "fresh"


def feed_freshness(session: Session) -> list[dict]:
    """Each registered feed + its LATEST refresh (time + status) + a fresh/due/overdue/failed status.
    A failed automated pull overrides freshness — a feed whose last scheduled refresh ERRORED is 'failed',
    even if it ran recently, because that stale-or-broken source can taint a filing until it's fixed."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (feed_key) feed_key, created_at AS last_refresh, status AS last_status, actor_user_id
        FROM feed_refresh_log ORDER BY feed_key, created_at DESC
    """)).mappings().all()
    last = {r["feed_key"]: r for r in rows}
    now = datetime.now(timezone.utc)
    out = []
    for f in FEEDS:
        r = last.get(f["key"])
        lr = r["last_refresh"] if r else None
        days = (now - lr).total_seconds() / 86400 if lr else None
        base = _status(days, f["cadence_days"])
        status = "failed" if (r and r["last_status"] == "failed") else base
        out.append({**f, "last_refresh": lr.isoformat() if lr else None,
                    "days_since": round(days, 1) if days is not None else None,
                    "next_due_days": (round(max(0.0, f["cadence_days"] - days), 1) if days is not None else None),
                    "last_status": r["last_status"] if r else None,
                    "last_by": ("auto" if (r and r["actor_user_id"] is None) else "manual") if r else None,
                    "status": status})
    return out


def overdue_basis_feeds(session: Session) -> list[dict]:
    """Feeds that (a) drive an un-frozen filing (`invalidates_basis`) AND (b) are overdue OR whose last
    automated refresh FAILED. The pre-filing control: surface these so the operator fixes the golden
    source BEFORE a stale/broken figure reaches a filing (audit T4, staleness layer)."""
    return [{"key": f["key"], "name": f["name"], "days_since": f["days_since"],
             "cadence_days": f["cadence_days"], "status": f["status"]}
            for f in feed_freshness(session)
            if f["invalidates_basis"] and f["status"] in ("overdue", "failed")]


def basis_freshness_at(session: Session) -> dict:
    """A compact freshness snapshot of the basis-driving feeds, to stamp into a frozen filing so an
    auditor can see how current the golden source was at freeze time."""
    return {f["key"]: f["status"] for f in feed_freshness(session) if f["invalidates_basis"]}


def record_refresh(session: Session, feed_key: str, actor_user_id: str | None,
                   note: str | None = None, status: str = "refreshed") -> dict:
    """Append a refresh event to the log. actor_user_id=None means the SYSTEM (scheduled auto-refresh);
    a user id means a manual override. status is 'refreshed' or 'failed'. This records that the scheduled
    ingestion ran — the heavy data pull is the adapter's job (honest boundary, unchanged)."""
    if feed_key not in _BY_KEY:
        raise ValueError(f"unknown feed '{feed_key}'")
    row = session.execute(text("""
        INSERT INTO feed_refresh_log (feed_key, status, note, actor_user_id)
        VALUES (:k, :s, :n, :u) RETURNING refresh_id, created_at
    """), {"k": feed_key, "s": status, "n": note, "u": actor_user_id}).mappings().first()
    session.commit()
    return {"feed_key": feed_key, "refresh_id": str(row["refresh_id"]), "status": status,
            "created_at": row["created_at"].isoformat(),
            "invalidates_basis": _BY_KEY[feed_key]["invalidates_basis"]}


# ── Automated refresh ────────────────────────────────────────────────────────────────────────────────
# Production wires each feed's real ingestion adapter here; a hook does the pull and returns None on
# success or raises on failure. Until an adapter is wired, the default path records the scheduled tick
# (same boundary as the manual button — the log records that the scheduled ingestion ran). A hook that
# raises records a 'failed' event, which the monitor shows in red and surfaces as a pre-filing control.
_REFRESH_HOOKS: dict = {}


def register_refresh_hook(feed_key: str, fn) -> None:
    _REFRESH_HOOKS[feed_key] = fn


def refresh_one(session: Session, feed_key: str, actor_user_id: str | None = None) -> dict:
    """Run one feed's refresh (its adapter hook if wired, else record the scheduled tick). actor_user_id
    None = the scheduler; a user id = a manual 'Refresh now' override. Records refreshed OR failed."""
    if feed_key not in _BY_KEY:
        raise ValueError(f"unknown feed '{feed_key}'")
    try:
        hook = _REFRESH_HOOKS.get(feed_key)
        if hook:
            hook(session)
        who = "manual override" if actor_user_id else "scheduled ingestion"
        return record_refresh(session, feed_key, actor_user_id, note=f"auto-refresh ({who})", status="refreshed")
    except Exception as e:  # a real adapter failure must surface, not silently pass
        return record_refresh(session, feed_key, actor_user_id, note=f"refresh failed: {e}"[:400], status="failed")


def run_scheduled_refreshes(session: Session, force: bool = False) -> list[dict]:
    """The automation entry point (Celery beat calls this daily; scripts/refresh_feeds_now.py runs it
    once). For every auto-scheduled feed that is DUE by its cadence (or all of them when force=True),
    run its refresh and log the result. on_demand/planned/estimated feeds are intentionally skipped."""
    fresh = {x["key"]: x for x in feed_freshness(session)}
    done: list[dict] = []
    for f in FEEDS:
        if not f.get("auto_refresh"):
            continue
        ds = fresh[f["key"]]["days_since"]
        if force or ds is None or ds >= f["cadence_days"]:
            done.append(refresh_one(session, f["key"], actor_user_id=None))
    return done
