"""Every located asset of ONE organization, across all six sector tables, with its headline score at a horizon.

The sector modules each keep their own book (bank_assets, insurance_policies, assetmgmt_holdings,
realestate_properties, sc_company_sites, sc_sourcing_plots) and each has a physical-risk view. This is the one
cross-sector reader the regulator portal and the map layers use; it is org-type agnostic (a bank simply has empty
rows in the other five tables). Headline = max hazard score at (scenario, horizon), the same rule the sector pages use.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from services.portfolio_engine import DEFAULT_HEADLINE_EXCLUDE

# The four financial verticals live on the shared `entities` table and are read through the SAME portfolio engine
# the sector pages use (horizon interpolation, scenario-flat fallback, headline rule, buckets) — so a supervisor's
# number for an entity equals the number that entity sees on its own page.
_ENGINE_VERTICALS = {"banking": "financed asset", "insurance": "insured location", "assetmgmt": "holding", "realestate": "property"}

# Agriculture keeps its own tables (sites + sourcing plots) and physical-risk views.
_AGRI_SOURCES = [
    ("site", """        SELECT s.site_id AS id, s.name, s.latitude AS lat, s.longitude AS lon, s.country AS region,
               s.annual_value_eur AS value_eur, v.hazard_type AS hazard, v.physical_risk_score AS score
        FROM sc_company_sites s JOIN v_sc_site_physical_risk v ON v.site_id = s.site_id
        WHERE s.org_id = :o AND v.scenario = :sc AND v.time_horizon = :h"""),
    ("plot", """        SELECT p.plot_id AS id, COALESCE(p.plot_name, co.name) AS name, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.country, p.region) AS region, p.annual_spend_eur AS value_eur, v.hazard_type AS hazard,
               v.physical_risk_score AS score
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
        WHERE p.org_id = :o AND v.scenario = :sc AND v.time_horizon = :h"""),
]


def org_asset_points(session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                     source: str = "own", subject_org_id: Optional[str] = None) -> list[dict]:
    """[{id, name, kind, lat, lon, region, value_eur, score, hazard}] — one row per asset of the org across every
    sector table; headline = the sector engine's headline (worst standing hazard, nowcasts excluded). Unlocated
    assets are included (lat/lon None) so value-based metrics match the entity's own book; maps skip them."""
    from services.portfolio_engine import fetch_entities_with_risk
    out: list[dict] = []
    for vertical, label in _ENGINE_VERTICALS.items():
        for r in fetch_entities_with_risk(session, org_id, vertical, scenario, horizon, source=source, subject_org_id=subject_org_id):
            out.append({"id": f"{vertical}:{r['entity_id']}", "name": r.get("entity_name") or r.get("name") or label, "kind": label,
                        "lat": (float(r["lat"]) if r.get("lat") is not None else None),
                        "lon": (float(r["lon"]) if r.get("lon") is not None else None),
                        "region": r.get("region") or r.get("country"),
                        "value_eur": float(r.get("primary_value_eur") or 0),
                        "score": (float(r["headline_score"]) if r.get("headline_score") is not None else None),
                        "hazard": r.get("headline_hazard"), "nace_code": r.get("nace_code"), "country": r.get("country"),
                        "external_ref": r.get("external_ref"), "region_name": r.get("region"),
                        "location_precision": r.get("location_precision") or ("point" if r.get("lat") is not None else "unlocated")})
    if source != "own":
        return out          # shadow books exist for the engine verticals only
    by_id: dict[str, dict] = {}
    agri_rows = [(kind, session.execute(text(sql), {"o": org_id, "sc": scenario, "h": horizon}).mappings().all())
                 for kind, sql in _AGRI_SOURCES]
    if not any(rows for _, rows in agri_rows) and (scenario, horizon) != ("baseline", "current"):
        # agri views carry anchor horizons only; a supervisor asking for an off-anchor basis gets today's standing
        # scores, labelled as such — never an empty book passed off as "no exposure"
        agri_rows = [(kind, session.execute(text(sql), {"o": org_id, "sc": "baseline", "h": "current"}).mappings().all())
                     for kind, sql in _AGRI_SOURCES]
        basis = "baseline/current (no scores at the requested basis)"
    else:
        basis = None
    for kind, rows in agri_rows:
        for r in rows:
            key = f"{kind}:{r['id']}"
            a = by_id.setdefault(key, {"id": key, "name": r["name"], "kind": kind,
                                       "lat": (float(r["lat"]) if r["lat"] is not None else None),
                                       "lon": (float(r["lon"]) if r["lon"] is not None else None),
                                       "region": r["region"], "value_eur": float(r["value_eur"] or 0), "score": None, "hazard": None,
                                       **({"basis_note": basis} if basis else {})})
            sc = float(r["score"]) if r["score"] is not None else None
            if r["hazard"] in DEFAULT_HEADLINE_EXCLUDE:
                continue
            if sc is not None and (a["score"] is None or sc > a["score"]):
                a["score"], a["hazard"] = sc, r["hazard"]
    return out + list(by_id.values())
