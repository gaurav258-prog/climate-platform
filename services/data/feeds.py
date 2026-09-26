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
#   release     — a pinned, versioned dataset release landed to our store; it changes only when the publisher
#                 issues a new release (then re-landed and re-scored), so there is nothing to refresh on a clock
# `name` is the source we ACTUALLY ingest; any gap between that and the ideal source is stated in `note`.
FEEDS: list[dict] = [
    {"key": "climate_reanalysis", "name": "Copernicus / ECMWF — ERA5 / ERA5-Land", "category": "hazard",
     "cadence_days": 30, "invalidates_basis": True, "maturity": "live",
     "note": "Global climate reanalysis — heat, drought, frost, soil-water and wind. Global baselines are in place "
             "(temperature, precipitation, soil-moisture and frost climatologies), so scoring is worldwide."},
    {"key": "flood", "name": "ERA5-Land runoff (flood proxy)", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False, "maturity": "proxy",
     "note": "GloFAS discharge was withdrawn from the CDS in 2025; ERA5-Land total runoff stands in for it. This "
             "was the input of the earlier flood event model. It no longer drives the published flood score, "
             "which reads the JRC river-flood hazard maps (flood v3) — so a refresh does not change a filing."},
    {"key": "jrc_flood_maps", "name": "Copernicus EMS / JRC global river-flood hazard maps v2.1.2", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "LISFLOOD-FP inundation depth at ~90 m for the 1-in-10, 1-in-100 and 1-in-500-year floods, plus the "
             "permanent-water mask. Drives the flood score (v3). River flooding only: pluvial/flash and groundwater "
             "flooding are disclosed gaps, and the maps carry no flood defences (hazard, not residual risk)."},
    {"key": "fire_thermal", "name": "NASA FIRMS (VIIRS active fire)", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True, "maturity": "live",
     "note": "Active fire real. Sentinel-3 SLSTR heat integration is now LIVE via the CDSE Sentinel Hub "
             "Statistical API (per-H3-cell S8 10.85µm thermal-IR brightness temperature → lst_kelvin heat "
             "feature; activates once Copernicus Data Space credentials are configured). It is brightness temperature, not the "
             "emissivity-corrected L2 LST product (that is the raw-scene Path-B upgrade)."},
    {"key": "atmosphere", "name": "Copernicus CAMS", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False, "maturity": "on_demand",
     "note": "Air quality / dust / fire emissions, fetched per-query (not landed). Informs the risk view; "
             "E2 pollution is out of filing scope."},
    {"key": "imagery", "name": "Sentinel-1/2 (SAR + optical)", "category": "hazard",
     "cadence_days": 6, "invalidates_basis": True, "maturity": "planned",
     "note": "Sentinel-1 SAR flood integration is built and awaiting activation via the Copernicus Data Space "
             "Statistical API (per-cell terrain-corrected VV backscatter and a 7-day anomaly feeding the flood "
             "model). It activates once Copernicus Data Space credentials are configured; until production rows "
             "land, the feed is shown as Planned. Sentinel-2 NDVI integration is not yet in production. When SAR "
             "data is in production, flood moves from the ERA5 runoff proxy to observed inundation."},
    {"key": "storms_ocean", "name": "NOAA IBTrACS (cyclone tracks)", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": True, "maturity": "live",
     "note": "Tropical-cyclone tracks are in production; Copernicus Marine sea-state is not yet integrated."},
    {"key": "nasa_power", "name": "NASA POWER (MERRA-2) daily minimum and maximum temperature", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": False, "maturity": "live",
     "note": "30 years (1991-2020) of daily 2 m temperature at the location, read on demand from NASA POWER. Cold wave: "
             "the 1-in-10 coldest night and the location's 99.6 % design temperature, from the daily minima. Chronic "
             "heat: the count of days at or above 30 °C, from the daily maxima."},
    {"key": "geophysical", "name": "USGS seismic (global) · Smithsonian GVP", "category": "hazard",
     "cadence_days": 1, "invalidates_basis": False, "maturity": "partial",
     "note": "Seismic scores from the global USGS M>=5.0 catalogue plus physics; the "
             "EMSC/ESHM20 European raster is a secondary background layer, not the scoring path. GVP per-volcano "
             "event records for the curated backtest volcanoes; the global volcano catalogue is its own feed. "
             "Geophysical, not climate-attributable, therefore out of CSRD/EUDR filing scope."},
    {"key": "fire_climatology", "name": "Copernicus CEMS/ECMWF Fire Weather Index (EWDS) · C3S ESA-CCI burned area", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "live",
     "note": "Wildfire hazard climatology: Fire Weather Index extreme-danger days 2006-2020 combined with ESA-CCI "
             "burned-area history 2001-2019. Rebuilt annually."},
    {"key": "volcanic_gvp", "name": "Smithsonian GVP — Volcanoes of the World (Holocene catalogue, WFS)", "category": "hazard",
     "cadence_days": 30, "invalidates_basis": False, "maturity": "live",
     "note": "All ~1,200 Holocene volcanoes + ~11,000 catalogued eruptions (confirmed-eruption VEI history) drives the "
             "any-address volcanic screening score. Geophysical, therefore out of CSRD/EUDR filing scope."},
    {"key": "cmip6_ensemble", "name": "CMIP6 multi-model ensemble (4 models, Pangeo archive)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "Projected change in temperature, precipitation and near-surface wind versus 1995-2014, per SSP and "
             "period, as an ensemble mean and across-model spread on a 2° grid. Drives the changing-temperature, "
             "-precipitation and -wind channels and the forward horizons of flood, cyclone and wildfire."},
    {"key": "gesla_tide_gauges", "name": "GESLA-3 tide-gauge records (extreme still-water levels)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "The observed 1-in-10-year extreme still-water level at the nearest gauge (1,864 gauges with 10+ years, "
             "1979-2020) sets coastal freeboard; IPCC AR6 sea-level rise is added for forward horizons. Sites with no "
             "gauge within 250 km are not scored."},
    {"key": "elevation_dem", "name": "Copernicus GLO-90 DEM (elevation) · Natural Earth coastline", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "on_demand",
     "note": "Elevation at the site and a five-point slope stencil, read per location and cached per H3 cell, plus "
             "distance to the coastline. Feeds coastal flooding and saline intrusion (elevation and distance to the "
             "coast) and avalanche and solifluction (slope)."},
    {"key": "landslide_lhasa", "name": "NASA Global Landslide Susceptibility Map (LHASA)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "~1 km susceptibility classes from slope, geology, roads, fault zones and forest loss. Terrain "
             "predisposition, not a rainfall-triggered event forecast; does not vary by scenario."},
    {"key": "subsidence_egms", "name": "Copernicus European Ground Motion Service (EGMS) Ortho L3, 2020-2024", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "Observed InSAR vertical ground velocity (100 m, GNSS-calibrated). Drives subsidence v2 across the EEA; "
             "cells outside EGMS coverage fall back to the global susceptibility layer."},
    {"key": "subsidence_gss", "name": "Global Subsidence Susceptibility (Herrera-García et al. 2021)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "~1 km susceptibility classes from aquifer compaction, lithology, groundwater depletion and urban load. "
             "The subsidence score outside EGMS coverage."},
    {"key": "permafrost_obu", "name": "Northern Hemisphere permafrost probability (Obu et al. 2019, ESA)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "~1 km permafrost probability fraction, Northern Hemisphere north of 25°N. Drives permafrost thaw and, "
             "with slope, solifluction."},
    {"key": "soil_erosion_glosem", "name": "ESDAC GloSEM global soil erosion (Borrelli/Panagos)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "RUSLE-based soil loss by water erosion, t/ha/yr at ~100 m."},
    {"key": "soil_degradation_sdg", "name": "Trends.Earth SDG 15.3.1 degraded land (Conservation International)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "on_demand",
     "note": "UNCCD degraded / stable / improved land status, read per location from the published global raster "
             "(not landed)."},
    {"key": "coastal_erosion_liscoast", "name": "JRC LISCoAsT shoreline-change projections (Vousdoukas et al. 2020)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "Projected long-term shoreline retreat for sandy coasts under RCP4.5 / RCP8.5 at 2050 and 2100, landed "
             "to an H3 lookup. Forward-looking only: no present-day value."},
    {"key": "ocean_ph_oceansoda", "name": "OceanSODA-ETHZ surface-ocean pH (NOAA NCEI OCADS)", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "Recent-years mean surface-ocean pH on a global grid; applies only to coastal and marine assets."},
    {"key": "glacial_lakes_giglak", "name": "GIGLak global glacial-lake inventory", "category": "hazard",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "release",
     "note": "117k mapped glacial lakes with area, landed to an H3 exposure layer. A proximity screen, not a "
             "flow-routed outburst model."},
    {"key": "deforestation", "name": "Hansen Global Forest Change", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "on_demand",
     "note": "Annual forest-loss, read at EUDR determination time (not landed); re-run determinations on each release."},
    {"key": "natura2000", "name": "EEA Natura 2000 (protected areas)", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "partial",
     "attribution": "© European Environment Agency (EEA) — Natura 2000 (reused under the EEA re-use policy)",
     "note": "EU protected-area boundaries, precomputed to an H3 lookup; flags own sites / sourcing plots in or "
             "near a Natura 2000 area (ESRS E4). One annual EEA release; EU coverage. EEA data is reusable "
             "(incl. commercially) with acknowledgement — attribution shown."},
    {"key": "osm_protected", "name": "OpenStreetMap protected areas", "category": "nature",
     "cadence_days": 30, "invalidates_basis": True, "maturity": "partial",
     "attribution": "© OpenStreetMap contributors (ODbL)",
     "note": "Global coverage layer for protected areas outside the EU where the authoritative WDPA is "
             "licence-restricted. Community-sourced with uneven coverage: a screening layer, not an authoritative "
             "agency feed, and labelled as such."},
    {"key": "wdpa", "name": "WDPA (World Database on Protected Areas)", "category": "nature",
     "cadence_days": 30, "invalidates_basis": True, "maturity": "planned",
     "attribution": "UNEP-WCMC and IUCN — Protected Planet: WDPA (licensed via IBAT)",
     "note": "Global protected areas — the non-EU counterpart to Natura 2000. Available under an IBAT licence; "
             "integration pending."},
    {"key": "wdoecm", "name": "WD-OECM (other conservation measures)", "category": "nature",
     "cadence_days": 30, "invalidates_basis": True, "maturity": "planned",
     "attribution": "UNEP-WCMC and IUCN — Protected Planet: WD-OECM (licensed via IBAT)",
     "note": "Other Effective area-based Conservation Measures — companion to WDPA; widens ESRS E4 / TNFD "
             "coverage. Same commercial-licence position as WDPA — sourced via IBAT."},
    {"key": "kba", "name": "Key Biodiversity Areas (KBA)", "category": "nature",
     "cadence_days": 365, "invalidates_basis": True, "maturity": "planned",
     "attribution": "BirdLife International / KBA Partnership (licensed via IBAT)",
     "note": "Sites of significance for global biodiversity (KBA Partnership). Commercially licensed via IBAT "
             "alongside WDPA/WD-OECM; loaded from the licensed file into the same H3 lookup."},
    {"key": "reference_lei", "name": "GLEIF (LEI)", "category": "reference",
     "cadence_days": 7, "invalidates_basis": False, "maturity": "live",
     "note": "Legal-entity identifiers; changes rename entities, not risk scores."},
    {"key": "reference_assets", "name": "Sector-intensity estimates (NACE)", "category": "reference",
     "cadence_days": 90, "invalidates_basis": False, "maturity": "estimated",
     "note": "Emissions are sector-average intensity × revenue, not a facility-level emissions feed; values are "
             "labelled as estimated throughout."},
    {"key": "reference_countries", "name": "Unicode CLDR — countries, codes and currencies", "category": "reference",
     "cadence_days": 180, "invalidates_basis": False, "maturity": "live",
     "attribution": "Unicode CLDR (Unicode licence)",
     "note": "ISO 3166 codes (alpha-2, alpha-3, numeric), country names in the EU's official languages plus Norwegian "
             "and Turkish, and each country's current currency — so a customer's 'Deutschland', 'DEU' or 'UK' is "
             "matched to the right country. Pinned CLDR release; a name that could mean two countries is never matched."},
    {"key": "fx_imf", "name": "IMF Exchange Rates (ER) — monthly, currencies the ECB does not quote", "category": "reference",
     "cadence_days": 7, "invalidates_basis": False, "maturity": "live",
     "attribution": "Source: International Monetary Fund, Exchange Rates (ER) dataset",
     "note": "Month-end and monthly-average national currency per euro for ~180 countries (from 2010), direct from the "
             "IMF data API — the second official source after the ECB, for currencies such as the Ghanaian cedi, "
             "Vietnamese dong or Colombian peso. Published with a 1-2 month lag, so a month-end rate is used for up "
             "to 62 days; older is marked stale. Future-dated periods and periods before a currency's introduction "
             "are refused."},
    {"key": "fx_ecb", "name": "ECB euro foreign exchange reference rates (first source)", "category": "reference",
     "cadence_days": 1, "invalidates_basis": False, "maturity": "live",
     "attribution": "Source: European Central Bank (ECB) — euro foreign exchange reference rates",
     "note": "Daily reference rates for ~30 currencies, direct from the ECB (full history since 1999, then the last "
             "90 days each day, which heals missed days). Converts customer values given in other currencies to EUR "
             "at the rate for the book date; the ECB's own figure is kept beside the one we calculate with. A "
             "refresh whose newest rate is more than 5 days old is recorded as failed."},
    {"key": "commodity_prices_wb", "name": "World Bank Pink Sheet (commodity prices)", "category": "reference",
     "cadence_days": 30, "invalidates_basis": False, "maturity": "live",
     "attribution": "© World Bank — Commodity Markets 'Pink Sheet' (CC BY 4.0)",
     "note": "Monthly commodity + fertiliser prices (1960→), keyless. Used for input-cost pressure and cost-of-goods "
             "validation — 33 commodities. Updates monthly; refreshed automatically."},
    {"key": "commodity_prices_eu", "name": "EU agri-food data portal (olive oil · wine · dairy)", "category": "reference",
     "cadence_days": 7, "invalidates_basis": False, "maturity": "live",
     "attribution": "© European Commission — agri-food data portal (CC BY 4.0)",
     "note": "Weekly EU prices the Pink Sheet lacks — olive oil, wine, and dairy — aggregated to a monthly EU "
             "mean, keyless. Updates weekly; refreshed automatically. Almond prices are not yet included."},
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
