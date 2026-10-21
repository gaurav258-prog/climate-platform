"""Golden-source feed registry + freshness — is the data under a filing current?

A filing is only as current as the feeds beneath it. Each source refreshes on its own clock; a compliance
officer needs to see, at a glance, when each was last refreshed and whether it's due. This is the tracking
layer: the registry (what feeds exist, how often they should refresh, and whether a refresh invalidates a
live/un-frozen basis) plus freshness computed against the append-only `feed_refresh_log`.

The actual data pulls stay where they belong — scheduled ingestion jobs, external. Recording a refresh here
stamps the log (and can trigger a re-score); it does not itself fetch data. Honest about the boundary.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages

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
#   proxy       — a real feed, but standing in for a different source (named in its words)
#   partial     — real but limited coverage (named in its words)
#   estimated   — derived (e.g. sector-average), not a measured feed
#   planned     — adapter is stub / not yet in production
#   release     — a pinned, versioned dataset release landed to our store; it changes only when the publisher
#                 issues a new release (then re-landed and re-scored), so there is nothing to refresh on a clock
# A feed's customer words — its name (the source we ACTUALLY ingest) and what it is and drives, with any gap between
# that and the ideal source — are the catalogue message platform.feed.<key> (data/reference/messages.en.json), set on
# each entry below as `name`, `note` and `message`; the comments beside the entries keep the engineering detail.
FEEDS: list[dict] = [
    {"key": "climate_reanalysis", "category": "hazard", "cadence_days": 30, "invalidates_basis": True, "maturity": "live"},
    # GloFAS discharge was withdrawn from the CDS in 2025; ERA5-Land total runoff stands in. Input of the earlier
    # flood event model; the published flood score (v3) reads jrc_flood_maps.
    {"key": "flood", "category": "hazard", "cadence_days": 1, "invalidates_basis": False, "maturity": "proxy"},
    # Copernicus EMS / JRC global river-flood hazard maps v2.1.2: LISFLOOD-FP inundation depth, RP10/100/500 +
    # permanent-water mask; drives flood v3 outside Europe (the European maps v3.1.1, data/datasets/jrc_flood_europe,
    # drive v4 inside the countries they cover).
    {"key": "jrc_flood_maps", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # Sentinel-3 SLSTR via the CDSE Sentinel Hub Statistical API: per-H3-cell S8 10.85 µm brightness temperature →
    # lst_kelvin heat feature; activates with Copernicus Data Space credentials. Emissivity-corrected L2 LST is
    # the raw-scene Path-B upgrade.
    {"key": "fire_thermal", "category": "hazard", "cadence_days": 1, "invalidates_basis": True, "maturity": "live"},
    # fetched per query (not landed); E2 pollution is out of filing scope.
    {"key": "atmosphere", "category": "hazard", "cadence_days": 1, "invalidates_basis": False, "maturity": "on_demand"},
    # Sentinel-1 GRD: per-cell terrain-corrected VV backscatter + 7-day anomaly via the CDSE Statistical API
    # (activates with credentials; maturity stays planned until production rows land). Sentinel-2 NDVI not in
    # production.
    {"key": "imagery", "category": "hazard", "cadence_days": 6, "invalidates_basis": True, "maturity": "planned"},
    {"key": "storms_ocean", "category": "hazard", "cadence_days": 1, "invalidates_basis": True, "maturity": "live"},
    # MERRA-2 based; daily T2M min/max 1991-2020 read on demand.
    {"key": "nasa_power", "category": "hazard", "cadence_days": 365, "invalidates_basis": False, "maturity": "live"},
    # USGS M>=5.0 catalogue + physics; EMSC/ESHM20 raster is a secondary background layer, not the scoring path;
    # GVP event records for the curated backtest volcanoes.
    {"key": "geophysical", "category": "hazard", "cadence_days": 1, "invalidates_basis": False, "maturity": "partial"},
    # Copernicus CEMS/ECMWF FWI (EWDS) extreme-danger days 2006-2020 · C3S ESA-CCI burned area 2001-2019.
    {"key": "fire_climatology", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "live"},
    # GVP Holocene catalogue over WFS; confirmed-eruption VEI history.
    {"key": "volcanic_gvp", "category": "hazard", "cadence_days": 30, "invalidates_basis": False, "maturity": "live"},
    # 4 models from the Pangeo archive; SSP × period ensemble mean and spread, 2° grid.
    {"key": "cmip6_ensemble", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # GESLA-3; IPCC AR6 SLR added for forward horizons.
    {"key": "gesla_tide_gauges", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # Copernicus GLO-90 DEM, five-point slope stencil, cached per H3 cell; Natural Earth coastline.
    {"key": "elevation_dem", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "on_demand"},
    # LHASA global susceptibility map.
    {"key": "landslide_lhasa", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # EGMS Ortho L3 2020-2024, GNSS-calibrated; drives subsidence v2 across the EEA; falls back to subsidence_gss.
    {"key": "subsidence_egms", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    {"key": "subsidence_gss", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # ESA CCI permafrost (Obu et al. 2019).
    {"key": "permafrost_obu", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # ESDAC GloSEM, RUSLE-based.
    {"key": "soil_erosion_glosem", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # Trends.Earth SDG 15.3.1 raster, read per location (not landed).
    {"key": "soil_degradation_sdg", "category": "hazard", "cadence_days": 365,
     "invalidates_basis": True, "maturity": "on_demand"},
    # JRC LISCoAsT, landed to an H3 lookup; forward-looking only.
    {"key": "coastal_erosion_liscoast", "category": "hazard", "cadence_days": 365,
     "invalidates_basis": True, "maturity": "release"},
    # NOAA NCEI OCADS.
    {"key": "ocean_ph_oceansoda", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    # landed to an H3 exposure layer; proximity screen, not flow-routed.
    {"key": "glacial_lakes_giglak", "category": "hazard", "cadence_days": 365, "invalidates_basis": True, "maturity": "release"},
    {"key": "deforestation", "category": "nature", "cadence_days": 365, "invalidates_basis": True, "maturity": "on_demand"},
    # precomputed to an H3 lookup (ESRS E4).
    {"key": "natura2000", "category": "nature", "cadence_days": 365,
     "invalidates_basis": True, "maturity": "partial",
     "attribution": "© European Environment Agency (EEA) — Natura 2000 (reused under the EEA re-use policy)"},
    {"key": "osm_protected", "category": "nature", "cadence_days": 30,
     "invalidates_basis": True, "maturity": "partial",
     "attribution": "© OpenStreetMap contributors (ODbL)"},
    # IBAT licence pending.
    {"key": "wdpa", "category": "nature", "cadence_days": 30,
     "invalidates_basis": True, "maturity": "planned",
     "attribution": "UNEP-WCMC and IUCN — Protected Planet: WDPA (licensed via IBAT)"},
    # ESRS E4 / TNFD; IBAT licence, same position as WDPA.
    {"key": "wdoecm", "category": "nature", "cadence_days": 30,
     "invalidates_basis": True, "maturity": "planned",
     "attribution": "UNEP-WCMC and IUCN — Protected Planet: WD-OECM (licensed via IBAT)"},
    # loaded from the licensed file into the same H3 lookup once licensed.
    {"key": "kba", "category": "nature", "cadence_days": 365,
     "invalidates_basis": True, "maturity": "planned",
     "attribution": "BirdLife International / KBA Partnership (licensed via IBAT)"},
    {"key": "reference_lei", "category": "reference", "cadence_days": 7, "invalidates_basis": False, "maturity": "live"},
    {"key": "reference_assets", "category": "reference", "cadence_days": 90, "invalidates_basis": False, "maturity": "estimated"},
    {"key": "reference_countries", "category": "reference", "cadence_days": 180,
     "invalidates_basis": False, "maturity": "live",
     "attribution": "Unicode CLDR (Unicode licence)"},
    {"key": "fx_imf", "category": "reference", "cadence_days": 7,
     "invalidates_basis": False, "maturity": "live",
     "attribution": "Source: International Monetary Fund, Exchange Rates (ER) dataset"},
    {"key": "fx_ecb", "category": "reference", "cadence_days": 1,
     "invalidates_basis": False, "maturity": "live",
     "attribution": "Source: European Central Bank (ECB) — euro foreign exchange reference rates"},
    # keyless API.
    {"key": "commodity_prices_wb", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live",
     "attribution": "© World Bank — Commodity Markets 'Pink Sheet' (CC BY 4.0)"},
    # FAOSTAT QCL; a reviewed feed (E148): staged → reviewed → landed.
    {"key": "crop_production_faostat", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live", "review": True,
     "attribution": "Source: FAO, FAOSTAT — Crops and livestock products (CC BY 4.0)"},
    # Eurostat apro_cpsh1; reviewed feed.
    {"key": "crop_production_eurostat", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live", "review": True,
     "attribution": "Source: Eurostat, apro_cpsh1 — Crop production in EU standard humidity"},
    # Eurostat apro_cpshr (NUTS 2021); NUTS-1, extra-regio and other-NUTS-version codes set aside; reviewed feed.
    {"key": "crop_production_eurostat_regional", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live", "review": True,
     "attribution": "Source: Eurostat, apro_cpshr — Crop production in EU standard humidity by NUTS 2 region"},
    # USDA FAS PSD; reviewed feed.
    {"key": "crop_production_usda_fas", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live", "review": True,
     "attribution": "Source: USDA Foreign Agricultural Service, PSD database"},
    # NASS Quick Stats; ISO 3166-2 from the Census Bureau's state list; 'YEAR' forecast rows set aside; reviewed feed.
    {"key": "crop_production_usda_nass", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live", "review": True,
     "attribution": "Source: USDA National Agricultural Statistics Service, Quick Stats"},
    # NASS Quick Stats county estimates; reviewed feed.
    {"key": "crop_production_usda_nass_county", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live", "review": True,
     "attribution": "Source: USDA National Agricultural Statistics Service, Quick Stats (county estimates)"},
    # Statistics Canada table 32-10-0359-01, checked against the file's HTTP validators; reviewed feed.
    {"key": "crop_production_statcan", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live", "review": True,
     "attribution": "Source: Statistics Canada, Table 32-10-0359-01 (Statistics Canada Open Licence)"},
    # checked against the CDS month list (no download); calibrations re-run, publication changes proposed for
    # review (E163).
    {"key": "weather_era5_land_global", "category": "reference", "cadence_days": 30,
     "invalidates_basis": False, "maturity": "live",
     "attribution": "Contains modified Copernicus Climate Change Service information (ERA5-Land monthly averaged data)"},
    # keyless API.
    {"key": "commodity_prices_eu", "category": "reference", "cadence_days": 7,
     "invalidates_basis": False, "maturity": "live",
     "attribution": "© European Commission — agri-food data portal (CC BY 4.0)"},
]
_BY_KEY = {f["key"]: f for f in FEEDS}

# A feed is on the AUTOMATED scheduler when it has a landed ingestion path (live/proxy/partial). on_demand
# feeds refresh per-query, `planned` ones aren't wired, and `estimated` coefficients aren't a live feed —
# those are NOT auto-scheduled, and the monitor says so honestly rather than pretending they self-refresh.
_AUTO_MATURITY = {"live", "proxy", "partial"}
for _f in FEEDS:
    _f["auto_refresh"] = _f["maturity"] in _AUTO_MATURITY


def words_code(feed_key: str) -> str:
    """The catalogue code of a feed's words: platform.feed.<key>, without the key's digits (a catalogue code is
    letters only, and cmip6_ensemble, natura2000 and weather_era5_land_global carry digits)."""
    return "platform.feed." + re.sub(r"\d", "", feed_key)


for _f in FEEDS:      # the words every screen, filing methodology and assurance pack names the feed with
    _m = messages.render(words_code(_f["key"]))
    _f["name"], _f["note"], _f["message"] = _m["label"], " ".join(_m["detail"].values()), _m


# Which source feed(s) a hazard's score is derived from. canonical_scores carries no feed FK — the link is
# by construction (a hazard is scored from these feeds), so this registry IS the score→source provenance a
# lineage trace needs. Kept honest: a hazard maps only to feeds that genuinely drive it. Ordered primary-first.
HAZARD_FEEDS: dict[str, list[str]] = {
    "flood":         ["jrc_flood_maps", "cmip6_ensemble"],  # JRC maps (v3 score); CMIP6 for forward horizons
    "coastal_flood": ["gesla_tide_gauges", "elevation_dem"],# gauge extreme water level + site elevation; AR6 SLR is a model constant
    "heat_acute":    ["climate_reanalysis"],
    "heat_chronic":  ["nasa_power"],                        # NASA POWER daily Tmax 1991-2020 (v2)
    "drought":       ["climate_reanalysis"],                # ERA5-Land SPEI/soil-moisture
    "soil_water":    ["climate_reanalysis"],
    "frost":         ["climate_reanalysis"],                # ERA5 min-temperature
    "cold_wave":     ["nasa_power"],                        # NASA POWER daily Tmin 1991-2020
    "wildfire":      ["fire_climatology", "climate_reanalysis", "cmip6_ensemble"],  # FWI/burn climatology; ERA5 nowcast; CMIP6 forward
    "storm":         ["storms_ocean", "cmip6_ensemble"],    # IBTrACS tracks; CMIP6 for forward horizons
    "windstorm":     ["climate_reanalysis"],                # ERA5 10 m gust climatology
    "severe_convective": ["climate_reanalysis"],            # ERA5 CAPE × 0-6 km shear (anchored to NOAA SPC reports)
    "heavy_precip":  ["climate_reanalysis"],                # ERA5 monthly precipitation climatology
    "temp_variability":   ["climate_reanalysis"],           # ERA5 monthly temperature climatology
    "precip_variability": ["climate_reanalysis"],           # ERA5 monthly precipitation climatology
    "changing_temp":   ["cmip6_ensemble"],
    "changing_precip": ["cmip6_ensemble"],
    "changing_wind":   ["cmip6_ensemble"],
    "landslide":     ["landslide_lhasa"],
    "subsidence":    ["subsidence_egms", "subsidence_gss"], # observed InSAR (EEA) else susceptibility class
    "permafrost":    ["permafrost_obu"],
    "solifluction":  ["permafrost_obu", "elevation_dem"],
    "avalanche":     ["elevation_dem"],                     # DEM slope × elevation/latitude snow proxy
    "saline_intrusion": ["elevation_dem"],                  # low-elevation coastal zone × AR6 SLR
    "soil_erosion":  ["soil_erosion_glosem"],
    "soil_degradation": ["soil_degradation_sdg"],
    "coastal_erosion":  ["coastal_erosion_liscoast"],
    "ocean_acidification": ["ocean_ph_oceansoda"],
    "glacial_lake_outburst": ["glacial_lakes_giglak"],
    "seismic":       ["geophysical"],                       # USGS
    "volcanic":      ["volcanic_gvp", "geophysical"],       # GVP global catalogue (+ curated zones)
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
    waiting = _awaiting_review(session)
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
                    "status": status,
                    # a reviewed feed (E148): a fetched release that has not landed yet — the store still holds the
                    # previous data until two operators approve it
                    "awaiting_review": waiting.get(f["key"]) if f.get("review") else None})
    return out


def _awaiting_review(session: Session) -> dict:
    """{feed key: its open release} for every reviewed yield source (services.reference.yield_sources)."""
    from services.reference.crop_releases import pending
    from services.reference.yield_sources import all_sources
    out = {}
    for ys in all_sources():
        p = pending(session, ys)
        out[ys.feed_key] = {**p, "fetched_at": p["fetched_at"].isoformat()} if p else None
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
                   note: str | None = None, status: str = "refreshed", cause: str | None = None) -> dict:
    """Append a refresh event to the log. actor_user_id=None means the SYSTEM (scheduled auto-refresh);
    a user id means a manual override. status is 'refreshed' or 'failed'; a failure carries its cause —
    'source_unreachable' (the provider's side) or 'adapter_fault' (ours). This records that the scheduled
    ingestion ran — the heavy data pull is the adapter's job (honest boundary, unchanged)."""
    if feed_key not in _BY_KEY:
        raise ValueError(f"unknown feed '{feed_key}'")
    row = session.execute(text("""
        INSERT INTO feed_refresh_log (feed_key, status, note, actor_user_id, cause)
        VALUES (:k, :s, :n, :u, :c) RETURNING refresh_id, created_at
    """), {"k": feed_key, "s": status, "n": note, "u": actor_user_id, "c": cause}).mappings().first()
    session.commit()
    return {"feed_key": feed_key, "refresh_id": str(row["refresh_id"]), "status": status, "cause": cause,
            "note": note, "created_at": row["created_at"].isoformat(),
            "invalidates_basis": _BY_KEY[feed_key]["invalidates_basis"]}


# ── Automated refresh ────────────────────────────────────────────────────────────────────────────────
# Production wires each feed's real ingestion adapter here; a hook does the pull and returns None on
# success or raises on failure. Until an adapter is wired, the default path records the scheduled tick
# (same boundary as the manual button — the log records that the scheduled ingestion ran). A hook that
# raises records a 'failed' event, which the monitor shows in red and surfaces as a pre-filing control.
_REFRESH_HOOKS: dict = {}


def register_refresh_hook(feed_key: str, fn) -> None:
    _REFRESH_HOOKS[feed_key] = fn


def _hook_commodity_prices_wb(session: Session) -> None:
    from scripts.ingest_prices_worldbank import refresh
    refresh(session)


def _hook_commodity_prices_eu(session: Session) -> None:
    from scripts.ingest_prices_eu_agrifood import refresh
    refresh(session)


def _hook_volcanic_gvp(session: Session) -> None:
    from scripts.fetch_gvp_catalogue import refresh
    refresh()


def _hook_fx_ecb(session: Session) -> None:
    from services.reference.ecb_fx import refresh
    refresh(session)


register_refresh_hook("fx_ecb", _hook_fx_ecb)


def _hook_fx_imf(session: Session) -> None:
    from services.reference.imf_fx import refresh
    refresh(session)


register_refresh_hook("fx_imf", _hook_fx_imf)


def _hook_reference_countries(session: Session) -> None:
    from services.reference.countries import refresh
    refresh(session)


register_refresh_hook("reference_countries", _hook_reference_countries)


def _reviewed_yield_hook(source_key: str):
    def hook(session: Session) -> None:
        from services.reference.crop_releases import refresh
        from services.reference.yield_sources import get
        refresh(session, get(source_key))     # stages a new release for review; never lands it
    return hook


def _register_reviewed_yield_sources() -> None:
    """Every reviewed yield source refreshes under its feed (E157) — a new source is a YieldSource and a FEEDS entry,
    never another hand-written hook; a source without its feed entry (or the reverse) is refused at import."""
    from services.reference.yield_sources import all_sources
    sources = {ys.feed_key: ys.key for ys in all_sources()}
    reviewed = {f["key"] for f in FEEDS if f.get("review")}
    if set(sources) != reviewed:
        raise RuntimeError(f"reviewed feeds and yield sources differ: {sorted(set(sources) ^ reviewed)}")
    for feed_key, source_key in sources.items():
        register_refresh_hook(feed_key, _reviewed_yield_hook(source_key))


_register_reviewed_yield_sources()


def _hook_weather_era5_land_global(session: Session) -> None:
    """The cheap check: does Copernicus hold a full year or a current-year month the landed files lack? Only then is the
    refresh job queued (fetch → weather build → calibration re-run) — off this thread, one fetch at a time."""
    from datetime import datetime, timezone

    from scripts.fetch_era5_land_global import _requests, available_months, held_months
    year = datetime.now(timezone.utc).year
    if _requests(6) or len(available_months(year)) > held_months(year):
        from services.tasks.jobs import submit
        submit("calibration.refresh_weather")


register_refresh_hook("weather_era5_land_global", _hook_weather_era5_land_global)
register_refresh_hook("volcanic_gvp", _hook_volcanic_gvp)
register_refresh_hook("commodity_prices_wb", _hook_commodity_prices_wb)
register_refresh_hook("commodity_prices_eu", _hook_commodity_prices_eu)


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
        out = source_unreachable(e)
        return record_refresh(session, feed_key, actor_user_id, note=f"refresh failed: {_failure(e, out)}"[:400],
                              status="failed", cause="source_unreachable" if out else "adapter_fault")


class SourceUnreachable(RuntimeError):
    """An adapter's statement that its provider could not be reached, or kept answering with an outage, after the
    adapter's own retries — the provider's side, not a fault in our code. Raise it `from` the last error."""


# RFC 9110 §15.6.3-15.6.5: 502 Bad Gateway, 503 Service Unavailable, 504 Gateway Timeout — the server, or a gateway in
# front of it, says it cannot serve now. Any other status (a 4xx, a 500) may be our request and stays an adapter fault.
OUTAGE_STATUS = frozenset({502, 503, 504})


def source_unreachable(e: BaseException) -> bool:
    """True when a refresh failed on the provider's side: the provider could not be reached (a dropped or refused
    connection, a timeout, a network error), answered 502/503/504, or an adapter said so (SourceUnreachable). Read
    from the error and the errors it was raised from — explicitly (`raise … from e`), or in place of one (`from None`).
    An error that merely arose while another was being handled is not read through, so a fault in our adapter is never
    hidden as an outage."""
    import urllib.error

    import requests
    seen: set[int] = set()
    x: BaseException | None = e
    while x is not None and id(x) not in seen:
        seen.add(id(x))
        if isinstance(x, (SourceUnreachable, ConnectionError, TimeoutError, requests.ConnectionError, requests.Timeout)):
            return True
        if isinstance(x, requests.HTTPError):
            if x.response is not None and x.response.status_code in OUTAGE_STATUS:
                return True
        elif isinstance(x, urllib.error.HTTPError):
            if x.code in OUTAGE_STATUS:
                return True
        elif isinstance(x, urllib.error.URLError):
            return True
        x = x.__cause__ or (x.__context__ if x.__suppress_context__ else None)
    return False


def _failure(e: Exception, unreachable: bool) -> str:
    """A failure as the monitor states it: the source being out of reach is said so, so it is never mistaken for a
    fault in our adapter — and an adapter fault is never hidden as an outage."""
    return f"source unreachable ({type(e).__name__}): {e}" if unreachable else str(e)


# One scheduled refresh at a time on a database, and never during a test run (E178): Celery beat and the API's fallback
# ticker take this Postgres advisory lock for a whole scheduled tick; the test suite's demo-data guard (tests/conftest.py)
# holds it for the whole run. A tick that cannot take it is deferred — the next one refreshes whatever is due — so the
# platform's own writes (a staged release, an approval request) never land inside a test run's fingerprint window.
SCHEDULED_REFRESH_LOCK = 7_211_031_016


def run_scheduled_refreshes(session: Session, force: bool = False) -> list[dict]:
    """The automation entry point (Celery beat calls this hourly; scripts/refresh_feeds_now.py runs it
    once). For every auto-scheduled feed that is DUE by its cadence (or all of them when force=True),
    run its refresh and log the result. on_demand/planned/estimated feeds are intentionally skipped.
    A scheduled tick (force=False) runs only while it holds SCHEDULED_REFRESH_LOCK; otherwise it is deferred ([])."""
    if force:
        return _refresh_due(session, force=True)
    with session.get_bind().connect() as lock:
        if not lock.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SCHEDULED_REFRESH_LOCK}).scalar():
            import logging
            logging.getLogger(__name__).info("scheduled feed refresh deferred: another tick or a test run holds the lock")
            return []
        try:
            return _refresh_due(session, force=False)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SCHEDULED_REFRESH_LOCK})


def _refresh_due(session: Session, force: bool) -> list[dict]:
    fresh = {x["key"]: x for x in feed_freshness(session)}
    done: list[dict] = []
    for f in FEEDS:
        if not f.get("auto_refresh"):
            continue
        ds = fresh[f["key"]]["days_since"]
        if force or ds is None or ds >= f["cadence_days"]:
            done.append(refresh_one(session, f["key"], actor_user_id=None))
    return done


def ensure_basis_fresh(session: Session, min_retry_hours: float = 1.0) -> dict:
    """Pre-filing SAFETY NET (no scheduler needed): if any basis feed is overdue/failed, try its refresh right now
    (scheduler actor), then re-evaluate. Throttled — a feed attempted within `min_retry_hours` is not retried, so a
    broken adapter can't be hammered on every read; it stays honestly 'failed' and surfaced. Returns
    {attempted: [keys], overdue: [feeds still overdue after the attempt]}. Celery beat remains the primary
    scheduler in production; this makes a dev/demo stack — or a worker outage — self-healing at filing time."""
    before = overdue_basis_feeds(session)
    attempted: list[str] = []
    for f in before:
        ds = f.get("days_since")
        if ds is not None and ds * 24.0 < min_retry_hours:
            continue
        try:
            refresh_one(session, f["key"], actor_user_id=None)
            attempted.append(f["key"])
        except Exception:   # recorded as failed by the adapter path; surfaced by overdue_basis_feeds below
            attempted.append(f["key"])
    return {"attempted": attempted, "overdue": overdue_basis_feeds(session) if attempted else before}
