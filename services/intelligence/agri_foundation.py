"""How agriculture scores are produced — the figures behind the agriculture 'Data sources' page, in one read (UI
standard, 2026-10-16): what goes in (the climate, crop, forest and price sources, each with how current it is, and the
organisation's sourcing plots), what scoring makes of the plots (for each agriculture hazard, the plots scored and their
risk bands) and the euros (the supply engine's volume at risk, with the spend whose euro is
withheld). Every figure is read from the data; a source group's customer words are its message code
(agri.data.source.*), so the page carries no source names of its own."""
from __future__ import annotations

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages
from core.types import score_to_bucket

# the hazards the registry's agriculture models score (the list /v1/supply/models reads); shown only while active
HAZARDS = ("drought", "heat_acute", "soil_water", "frost")
BANDS = ("L", "M", "H", "VH")
GRID_RESOLUTION = 8            # sourcing plots join the scores on resolution-8 cells (sc_sourcing_plots.h3_cell)
# each source group: its message code, then the registered feeds behind it (services/data/feeds.py), primary first
SOURCES = (
    ("agri.data.source.climate", ("climate_reanalysis",)),
    ("agri.data.source.crop_weather", ("weather_era5_land_global",)),
    ("agri.data.source.crop_statistics", ("crop_production_faostat", "crop_production_eurostat",
                                          "crop_production_eurostat_regional", "crop_production_usda_fas",
                                          "crop_production_usda_nass", "crop_production_usda_nass_county",
                                          "crop_production_statcan")),
    ("agri.data.source.forest", ("deforestation",)),
    ("agri.data.source.prices", ("commodity_prices_wb", "commodity_prices_eu")),
)
# a group is as current as its least current feed
_WORST = ("failed", "overdue", "due_soon")


def _state(feeds: list[dict]) -> str:
    """One state for a source group: failed / overdue / due_soon / fresh / on_demand (read when a check runs) /
    untracked (no update recorded)."""
    got = {f["status"] for f in feeds}
    for s in _WORST:
        if s in got:
            return s
    if all(f["maturity"] == "on_demand" for f in feeds):
        return "on_demand"
    return "fresh" if "fresh" in got else "untracked"


def sources(session: Session) -> list[dict]:
    from services.data.feeds import feed_freshness
    fresh = {f["key"]: f for f in feed_freshness(session)}
    out = []
    for code, keys in SOURCES:
        feeds = [fresh[k] for k in keys if k in fresh]
        if not feeds:
            continue
        last = max((f["last_refresh"] for f in feeds if f["last_refresh"]), default=None)
        out.append({"code": code, "message": messages.render(code), "state": _state(feeds), "last_update": last,
                    "feeds": len(feeds)})
    return out


def scores(session: Session, org_id: str) -> dict:
    """The organisation's sourcing plots and what scoring makes of them: for each active agriculture hazard, how many
    plots are scored for today and in which risk band, and how many also have a live reading; then the climate
    scenarios and years the plots are also scored for, and the grid cell a plot is scored on."""
    active = [h for h in HAZARDS if h in set(session.execute(text("""
        SELECT hazard_type FROM model_registry WHERE is_active AND hazard_type = ANY(:h)
    """), {"h": list(HAZARDS)}).scalars().all())]
    book = session.execute(text("""
        SELECT COUNT(*) AS n, COUNT(DISTINCT commodity_id) AS crops, COALESCE(SUM(annual_spend_eur), 0)::float AS spend
        FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)
    """), {"o": org_id}).mappings().one()
    today = session.execute(text("""
        SELECT v.hazard_type, v.physical_risk_score AS score
        FROM sc_sourcing_plots p
        JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id AND v.scenario = 'baseline' AND v.time_horizon = 'current'
        WHERE p.org_id = CAST(:o AS uuid) AND v.hazard_type = ANY(:h) AND v.physical_risk_score IS NOT NULL
    """), {"o": org_id, "h": active}).mappings().all()
    live = dict(session.execute(text("""
        SELECT cs.hazard_type, COUNT(DISTINCT p.plot_id)
        FROM sc_sourcing_plots p
        JOIN canonical_scores cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL AND cs.score_lane = 'nowcast'
        WHERE p.org_id = CAST(:o AS uuid) AND cs.hazard_type = ANY(:h)
        GROUP BY 1
    """), {"o": org_id, "h": active}).all())
    views = session.execute(text("""
        SELECT DISTINCT cs.scenario, cs.time_horizon
        FROM sc_sourcing_plots p
        JOIN canonical_scores cs ON cs.h3_cell = p.h3_cell AND cs.valid_to IS NULL AND cs.score_lane = 'standing'
        WHERE p.org_id = CAST(:o AS uuid) AND cs.hazard_type = ANY(:h)
    """), {"o": org_id, "h": active}).all()
    hazards = []
    for h in active:
        mine = [r for r in today if r["hazard_type"] == h]
        if not mine and not live.get(h):
            continue
        bands = dict.fromkeys(BANDS, 0)
        for r in mine:
            bands[score_to_bucket(r["score"]).value] += 1
        hazards.append({"hazard": h, "plots": len(mine), "bands": bands, "live_plots": live.get(h, 0)})
    return {
        "plots": book["n"], "crops": book["crops"], "spend_eur": round(book["spend"]),
        "hazards": hazards,
        "scenarios": sorted({sc for sc, _ in views if sc != "baseline"}),
        "years": sorted({y for _, y in views if y != "current"}),
        "cell_km2": round(h3.average_hexagon_area(GRID_RESOLUTION, unit="km^2"), 2),
    }


def money(session: Session, org_id: str) -> dict:
    """The euros the scores lead to: the supply engine's volume at risk today, on the spend whose euro is published,
    and the spend whose euro is withheld (its crop model has not passed a test on past harvests at every origin)."""
    from services.intelligence.supply_cogs import project_org_supply
    r = project_org_supply(session, org_id)
    pending = [c for c in r.commodities if c.status == "pending"]       # no hazard score yet: € withheld too
    return {"spend_eur": round(r.ingredient_spend_eur), "volume_at_risk_eur": round(r.volume_at_risk_eur),
            "published_spend_eur": round(r.covered_spend_eur), "held_spend_eur": round(r.held_spend_eur),
            "pending_spend_eur": round(sum(c.annual_spend_eur for c in pending)),
            "crops": r.n_commodities, "published_crops": sum(1 for c in r.commodities if c.status == "scored"),
            "held_crops": r.n_held, "pending_crops": len(pending)}


def foundation(session: Session, org_id: str) -> dict:
    return {"sources": sources(session), "scores": scores(session, org_id), "money": money(session, org_id)}
