"""Every located asset of ONE organization, across all six sector tables, with its headline score at a horizon.

The sector modules each keep their own book (bank_assets, insurance_policies, assetmgmt_holdings,
realestate_properties, sc_company_sites, sc_sourcing_plots) and each has a physical-risk view. This is the one
cross-sector reader the regulator portal and the map layers use; it is org-type agnostic (a bank simply has empty
rows in the other five tables). Headline = max hazard score at (scenario, horizon), the same rule the sector pages use.
"""
from __future__ import annotations

from sqlalchemy import text

_SOURCES = [
    ("asset", "financed asset", """
        SELECT a.asset_id AS id, a.asset_name AS name, a.latitude AS lat, a.longitude AS lon,
               COALESCE(a.region, a.country) AS region, a.asset_value_eur AS value_eur, v.hazard_type AS hazard,
               v.physical_risk_score AS score
        FROM bank_assets a JOIN v_bank_asset_physical_risk v ON v.asset_id = a.asset_id
        WHERE a.org_id = :o AND a.latitude IS NOT NULL AND v.scenario = :sc AND v.time_horizon = :h"""),
    ("policy", "insured location", """
        SELECT p.policy_id AS id, p.policy_name AS name, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.region, p.country) AS region, p.sum_insured_eur AS value_eur, v.hazard_type AS hazard,
               v.physical_risk_score AS score
        FROM insurance_policies p JOIN v_insurance_policy_physical_risk v ON v.policy_id = p.policy_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc AND v.time_horizon = :h"""),
    ("holding", "holding", """
        SELECT h.holding_id AS id, h.holding_name AS name, h.latitude AS lat, h.longitude AS lon,
               COALESCE(h.region, h.country) AS region, h.position_value_eur AS value_eur, v.hazard_type AS hazard,
               v.physical_risk_score AS score
        FROM assetmgmt_holdings h JOIN v_assetmgmt_holding_physical_risk v ON v.holding_id = h.holding_id
        WHERE h.org_id = :o AND h.latitude IS NOT NULL AND v.scenario = :sc AND v.time_horizon = :h"""),
    ("property", "property", """
        SELECT p.property_id AS id, p.property_name AS name, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.region, p.country) AS region, p.property_value_eur AS value_eur, v.hazard_type AS hazard,
               v.physical_risk_score AS score
        FROM realestate_properties p JOIN v_realestate_property_physical_risk v ON v.property_id = p.property_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc AND v.time_horizon = :h"""),
    ("site", "operational site", """
        SELECT s.site_id AS id, s.name, s.latitude AS lat, s.longitude AS lon, s.country AS region,
               s.annual_value_eur AS value_eur, v.hazard_type AS hazard, v.physical_risk_score AS score
        FROM sc_company_sites s JOIN v_sc_site_physical_risk v ON v.site_id = s.site_id
        WHERE s.org_id = :o AND s.latitude IS NOT NULL AND v.scenario = :sc AND v.time_horizon = :h"""),
    ("plot", "sourcing plot", """
        SELECT p.plot_id AS id, COALESCE(p.plot_name, co.name) AS name, p.latitude AS lat, p.longitude AS lon,
               COALESCE(p.country, p.region) AS region, p.annual_spend_eur AS value_eur, v.hazard_type AS hazard,
               v.physical_risk_score AS score
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        JOIN v_sc_plot_physical_risk v ON v.plot_id = p.plot_id
        WHERE p.org_id = :o AND p.latitude IS NOT NULL AND v.scenario = :sc AND v.time_horizon = :h"""),
]


def org_asset_points(session, org_id: str, scenario: str = "baseline", horizon: str = "current") -> list[dict]:
    """[{id, name, kind, lat, lon, region, value_eur, score, hazard}] — one row per located asset, headline =
    worst hazard at the requested scenario/horizon. Unscored assets appear with score None."""
    by_id: dict[str, dict] = {}
    for kind, _label, sql in _SOURCES:
        for r in session.execute(text(sql), {"o": org_id, "sc": scenario, "h": horizon}).mappings():
            key = f"{kind}:{r['id']}"
            a = by_id.setdefault(key, {"id": key, "name": r["name"], "kind": kind, "lat": float(r["lat"]),
                                       "lon": float(r["lon"]), "region": r["region"],
                                       "value_eur": float(r["value_eur"] or 0), "score": None, "hazard": None})
            sc = float(r["score"]) if r["score"] is not None else None
            if sc is not None and (a["score"] is None or sc > a["score"]):
                a["score"], a["hazard"] = sc, r["hazard"]
    return list(by_id.values())
