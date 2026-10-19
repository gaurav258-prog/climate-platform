"""Horizon — the front door: the organisation's book on a globe, at today and at each modelled year ahead.

One reader, the same one the sector pages and the supervisor's map use (services.geo.org_assets.org_asset_points): the
financial books from the shared book through the portfolio engine (its headline rule — the worst hazard over the
scales that apply to the asset class — its horizon reading and its scenario-flat fallback), agriculture from its sites
and sourcing plots. Today is read on current climate (baseline / current, the score lane every page leads with); 2030,
2050 and 2100 on the chosen scenario. An asset is at risk at a year when its headline score is at or above the level
the organisation states (method.at_risk_level); without a stated level there is no at-risk count, only the gap.

The supervisor's front door is the same globe over its population, rolled up to regions (services.geo.regions — never
a site), from the entities the person may see (the caller passes them: api.routers.supervisor._supervised).

Every explanation is a catalogue message (core/messages.py, codes horizon.*); every name a catalogue name.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from core import messages

# the financial verticals of the shared book, by the id prefix org_asset_points gives them → the kind's catalogue key
_VERTICAL_KIND = {"banking": "financed_asset", "insurance": "insured_location", "assetmgmt": "holding", "realestate": "property"}
_FINANCIAL = {"bank", "insurer", "asset_manager", "reit"}


def stops(scenario: str) -> list[dict]:
    """The years the globe shows: the engine's modelled anchors (services.intelligence.horizon.ANCHORS) — today on
    current climate, the later years on the scenario."""
    from services.intelligence.horizon import ANCHORS
    return [{"key": label, "year": year, "scenario": "baseline" if label == "current" else scenario,
             "label": messages.name("horizon.stop", label) if label == "current" else str(year)}
            for year, label in ANCHORS]


def scenarios() -> list[dict]:
    from core.types import SCENARIO_VALUES
    return [{"key": s, "name": messages.name("scenario", s)} for s in SCENARIO_VALUES if s != "baseline"]


def _scoped_ids(session, org_id: str, entity_id: Optional[str]) -> Optional[set[str]]:
    """The asset ids (as org_asset_points writes them) of one reporting entity and everything below it; None = all."""
    if not entity_id:
        return None
    from services.governance.entities import subtree_ids
    eids = subtree_ids(session, org_id, entity_id)
    if not eids:
        return set()
    rows = session.execute(text("""
        SELECT vertical || ':' || entity_id::text FROM portfolio_entities
         WHERE org_id = CAST(:o AS uuid) AND source = 'own' AND reporting_entity_id::text = ANY(:e)
        UNION ALL SELECT 'site:' || site_id::text FROM sc_company_sites WHERE org_id = CAST(:o AS uuid) AND entity_id::text = ANY(:e)
        UNION ALL SELECT 'plot:' || plot_id::text FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid) AND entity_id::text = ANY(:e)
    """), {"o": org_id, "e": eids}).scalars().all()
    return set(rows)


def _kind(point_id: str) -> str:
    prefix = point_id.split(":", 1)[0]
    return _VERTICAL_KIND.get(prefix, prefix)          # 'site' / 'plot' are their own keys


def _facts(kind: str, p: dict, plot: Optional[dict]) -> list[dict]:
    """The few facts the asset card shows, each a catalogue label with a value read from the book."""
    from services.geo.cells import country_label
    from services.reference.countries import english_name
    from services.reference.nace import label as nace_label
    out = [{"label": messages.name("horizon.value", kind), "money": p["value_eur"], "flow": kind == "plot"}]
    if p.get("nace_code") and nace_label(p["nace_code"]):
        out.append({"label": messages.name("horizon.fact", "sector"), "text": nace_label(p["nace_code"])})
    if plot and plot.get("commodity"):
        out.append({"label": messages.name("horizon.fact", "commodity"), "text": plot["commodity"]})
    # the financial books carry a country code; an agricultural site or plot names its place by its country code
    code = p.get("country") or (p.get("region") if _is_code(p.get("region")) else None)
    country = english_name(code) or country_label(code)
    if country:
        out.append({"label": messages.name("horizon.fact", "country"), "text": country})
    return out


def book(session, org_id: str, org_type: Optional[str], scenario: str, entity_id: Optional[str] = None) -> dict:
    """The organisation's located book at each stop, its at-risk count against the stated level, and its totals."""
    from services.geo.org_assets import org_asset_points
    from services.money.params import at_risk, for_org
    method = for_org(session, org_id)
    level = method.get("method.at_risk_level")
    keep = _scoped_ids(session, org_id, entity_id)
    plan = stops(scenario)
    by_id: dict[str, dict] = {}
    for i, st in enumerate(plan):
        for p in org_asset_points(session, org_id, st["scenario"], st["key"]):
            if p.get("lat") is None or p.get("lon") is None or (keep is not None and p["id"] not in keep):
                continue
            a = by_id.get(p["id"])
            if a is None:
                a = by_id[p["id"]] = {"p": p, "score": [None] * len(plan), "hazard": [None] * len(plan)}
            a["score"][i] = round(p["score"], 1) if p.get("score") is not None else None
            a["hazard"][i] = p.get("hazard")
    plots = _plot_facts(session, org_id, [k.split(":", 1)[1] for k in by_id if k.startswith("plot:")])

    from services.intelligence.adaptation import actions_for
    assets = []
    for pid, a in by_id.items():
        p, kind = a["p"], _kind(pid)
        ref = pid.split(":", 1)[1]
        plot = plots.get(ref) if kind == "plot" else None
        lead = next((h for h in reversed(a["hazard"]) if h), None)
        assets.append({
            "id": pid, "ref": ref, "name": p["name"], "kind": kind, "kind_name": messages.name("horizon.kind", kind),
            "lat": p["lat"], "lon": p["lon"], "region": _place(p.get("region")),
            "value_eur": p["value_eur"], "score": a["score"], "hazard": a["hazard"],
            "at_risk": [at_risk(method, s) for s in a["score"]],
            "facts": _facts(kind, p, plot),
            # recognised adaptation measures are the operator's levers (its own sites and sourcing) — a lender, insurer
            # or investor acts through its decision on the exposure instead
            "adaptations": ((actions_for([lead]) or [{}])[0].get("actions", [])[:3] if kind in ("site", "plot") and lead else []),
            "notice": messages.render("horizon.plot.eudr_unread") if plot and plot.get("unread") else None,
            "decide": org_type in _FINANCIAL or org_type == "manufacturer",
            "record_href": f"/detail/{kind}/{ref}" if kind in ("site", "plot") else "/portfolio",
        })
    assets.sort(key=lambda x: -(x["value_eur"] or 0))

    n = len(assets)
    risk = None
    if level is not None:
        risk = [{"n": sum(1 for x in assets if x["at_risk"][i]),
                 "value_eur": round(sum(x["value_eur"] for x in assets if x["at_risk"][i]))} for i in range(len(plan))]
        about = messages.render("horizon.at_risk.basis", level=f"{level:g}", period_end=method.period_end.isoformat())
    else:
        about = messages.render("horizon.at_risk.not_stated", period_end=method.period_end.isoformat())
    return {"assets": assets, "n_assets": n, "book_value_eur": round(sum(x["value_eur"] for x in assets)),
            "n_unscored": sum(1 for x in assets if x["score"][0] is None),
            "at_risk": {"level": level, "by_stop": risk, "message": about,
                        "gap": None if level is not None else "not stated: method.at_risk_level"}}


def _plot_facts(session, org_id: str, plot_ids: list[str]) -> dict[str, dict]:
    """Each sourcing plot's commodity and whether it is an EUDR plot with no current forest reading."""
    if not plot_ids:
        return {}
    from services.eudr.reading import for_org
    unread = {pid for pid, r in for_org(session, org_id, covered_only=True).items() if r is None}
    rows = session.execute(text("""SELECT p.plot_id::text AS id, co.name AS commodity FROM sc_sourcing_plots p
                                   JOIN sc_commodities co ON co.commodity_id = p.commodity_id
                                   WHERE p.org_id = CAST(:o AS uuid) AND p.plot_id::text = ANY(:ids)"""),
                           {"o": org_id, "ids": plot_ids}).mappings().all()
    return {r["id"]: {"commodity": r["commodity"], "unread": r["id"] in unread} for r in rows}


def population(session, entities: list[dict], scenario: str) -> dict:
    """The supervised population's exposure on the globe, rolled up to regions (NUTS-3, an H3 hexagon elsewhere): at
    each stop a region's highest headline score across the sites in it — the regional unit a supervisor sees, never a
    site. A region's point is a point inside its own boundary, never a site's coordinates."""
    from shapely.geometry import shape

    from services.geo.org_assets import org_asset_points
    from services.geo.regions import aggregate_by_region
    plan = stops(scenario)
    regions: dict[str, dict] = {}
    for i, st in enumerate(plan):
        points = []
        for e in entities:
            for p in org_asset_points(session, e["org_id"], st["scenario"], st["key"]):
                if p.get("lat") is not None and p.get("lon") is not None:
                    points.append({**p, "entity": e["name"]})
        for g in aggregate_by_region(points):
            r = regions.get(g["key"])
            if r is None:
                pt = shape(g["geometry"]).representative_point()
                r = regions[g["key"]] = {
                    "id": g["key"], "ref": g["key"], "name": g["name"], "kind": "region",
                    "kind_name": messages.name("horizon.kind", "region"), "lat": pt.y, "lon": pt.x,
                    "region": _country(g.get("country")), "value_eur": g["value_eur"],
                    "score": [None] * len(plan), "hazard": [None] * len(plan), "at_risk": [None] * len(plan),
                    "facts": [{"label": messages.name("horizon.value", "region"), "money": g["value_eur"], "flow": False},
                              {"label": messages.name("horizon.fact", "sites"), "text": str(g["n_sites"])},
                              {"label": messages.name("horizon.fact", "entities"), "text": str(len(g["entities"]))}],
                    "adaptations": [], "notice": None, "decide": False, "record_href": "/supervisor/map"}
            r["score"][i] = g["max_score"]
            r["hazard"][i] = g["worst_hazard"]
    out = sorted(regions.values(), key=lambda x: -(x["value_eur"] or 0))
    return {"assets": out, "n_assets": len(out), "book_value_eur": round(sum(x["value_eur"] for x in out)),
            "n_unscored": sum(1 for x in out if x["score"][0] is None),
            "at_risk": {"level": None, "by_stop": None, "gap": None, "message": messages.render("horizon.population.basis")}}


def _place(region: Optional[str]) -> str:
    """Where an asset is, in words: its region as the book names it, or its country's name where the book holds only a
    country code (an agricultural site, a plot without a region)."""
    from services.reference.countries import english_name
    if not region:
        return ""
    return (english_name(region) or region) if _is_code(region) else region


def _is_code(s: Optional[str]) -> bool:
    """A country code as the books write one ('ES', 'PRT', 'EL'), not a place name."""
    return bool(s) and s.isupper() and len(s) <= 3


def _country(code: Optional[str]) -> str:
    from services.geo.cells import country_label
    from services.reference.countries import english_name
    return (english_name(code) or country_label(code) or "") if code else ""


def entity_counts(session, org_id: str) -> list[dict]:
    """The reporting entities the person can scope Horizon to, each with the located assets in it and below it."""
    rows = session.execute(text("""
        WITH RECURSIVE tree AS (
            SELECT entity_id AS top, entity_id FROM reporting_entities WHERE org_id = CAST(:o AS uuid)
            UNION ALL
            SELECT t.top, c.entity_id FROM tree t JOIN reporting_entities c ON c.parent_entity_id = t.entity_id
        ), held AS (
            SELECT reporting_entity_id AS eid FROM portfolio_entities
             WHERE org_id = CAST(:o AS uuid) AND source = 'own' AND latitude IS NOT NULL
            UNION ALL SELECT entity_id FROM sc_company_sites WHERE org_id = CAST(:o AS uuid) AND latitude IS NOT NULL
            UNION ALL SELECT entity_id FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid) AND latitude IS NOT NULL
        )
        SELECT e.entity_id::text AS entity_id, e.name, e.kind,
               (SELECT count(*) FROM tree t JOIN held h ON h.eid = t.entity_id WHERE t.top = e.entity_id) AS n_assets
          FROM reporting_entities e WHERE e.org_id = CAST(:o AS uuid) ORDER BY e.name
    """), {"o": org_id}).mappings().all()
    return [{"entity_id": r["entity_id"], "name": r["name"], "kind": r["kind"],
             "kind_name": messages.name("entity_kind", r["kind"]), "n_assets": int(r["n_assets"])} for r in rows]


def role_names(org_type: Optional[str], roles: list[str]) -> list[dict]:
    """The person's roles in customer words: a supervisory body's from its role templates (the supervision profile
    registry's labels), every other organisation's from the catalogue."""
    if org_type == "regulator":
        from services.supervision.profiles import role_templates
        t = role_templates()
        return [{"key": r, "name": t[r]["label"] if isinstance(t.get(r), dict) else messages.name("role", r)} for r in roles]
    return [{"key": r, "name": messages.name("role", r)} for r in roles]
