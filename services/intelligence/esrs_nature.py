"""ESRS Climate & Nature disclosure pack — the topics our golden source genuinely supports.

CSRD/ESRS is one statement, but only some of it is *ours*: the topics that run off the satellite +
hazard + per-plot-geolocation + deforestation engine. This assembles those into one pack —
  E1  Climate change · physical risk   (reuses services.intelligence.csrd_e1)
  E3  Water                            (water-stress / soil-water exposure of sites & sourcing)
  E4  Biodiversity & ecosystems        (deforestation, from the EUDR determinations)
— and is explicit about what it does NOT cover (GHG accounting, pollution, circular economy, social,
governance), which belong to the customer's carbon / HR tooling. See docs/AGRI_REGULATORY_SCOPE.md.

Honesty carries through: a euro is a firm figure only where the chain is validated; deforestation is
reported only where we actually determined it (never a green we didn't earn).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.csrd_e1 import build_e1_report

WATER_HAZARDS = ("water_stress", "soil_water")
MATERIAL = 40

# ESRS topics we deliberately DON'T produce — surfaced so the customer sees the boundary, not a gap.
OUT_OF_SCOPE = [
    {"topic": "E1 (GHG)", "label": "GHG accounting — Scope 1/2/3 emissions", "handled_by": "your carbon-accounting tool"},
    {"topic": "E2", "label": "Pollution", "handled_by": "your EHS / carbon tool"},
    {"topic": "E5", "label": "Resource use & circular economy", "handled_by": "your operations / carbon tool"},
    {"topic": "S1–S4", "label": "Own workforce, value-chain workers, communities, consumers", "handled_by": "your HR / social-reporting tool"},
    {"topic": "G1", "label": "Business conduct / governance", "handled_by": "your governance / legal tool"},
]


def water_topic(session: Session, org_id: str, threshold: int = MATERIAL) -> dict:
    """ESRS E3 — assets & sourcing exposed to water stress (worst water hazard per site/plot)."""
    sites = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE w.score >= :m) exposed,
               COALESCE(SUM(s.annual_value_eur) FILTER (WHERE w.score >= :m), 0) value_exposed
        FROM sc_company_sites s
        LEFT JOIN LATERAL (
            SELECT MAX(physical_risk_score) score FROM v_sc_site_physical_risk v
            WHERE v.site_id = s.site_id AND v.scenario='baseline' AND v.time_horizon='current'
              AND v.hazard_type = ANY(:hz)) w ON true
        WHERE s.org_id = :o
    """), {"o": org_id, "m": threshold, "hz": list(WATER_HAZARDS)}).mappings().first()
    plots = session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE w.score >= :m) exposed,
               COALESCE(SUM(p.annual_spend_eur) FILTER (WHERE w.score >= :m), 0) spend_exposed,
               ROUND(MAX(w.score)::numeric, 1) peak
        FROM sc_sourcing_plots p
        LEFT JOIN LATERAL (
            SELECT MAX(physical_risk_score) score FROM v_sc_plot_physical_risk v
            WHERE v.plot_id = p.plot_id AND v.scenario='baseline' AND v.time_horizon='current'
              AND v.hazard_type = ANY(:hz)) w ON true
        WHERE p.org_id = :o
    """), {"o": org_id, "m": threshold, "hz": list(WATER_HAZARDS)}).mappings().first()
    material = (sites["exposed"] or 0) > 0 or (plots["exposed"] or 0) > 0
    return {
        "topic": "E3", "title": "Water", "standard": "ESRS E3 — Water and marine resources",
        "material": material,
        "own_operations": {"sites": sites["n"], "sites_water_stressed": sites["exposed"], "asset_value_exposed_eur": float(sites["value_exposed"] or 0)},
        "upstream": {"plots": plots["n"], "plots_water_stressed": plots["exposed"], "spend_exposed_eur": float(plots["spend_exposed"] or 0), "peak_score": float(plots["peak"]) if plots["peak"] is not None else None},
        "basis": f"Worst standing water hazard (water stress / soil-water deficit) per site & plot, Copernicus/ECMWF-indexed; 'exposed' = score ≥ {threshold}.",
    }


def biodiversity_topic(session: Session, org_id: str) -> dict:
    """ESRS E4 — deforestation across the sourcing book, from the EUDR satellite determinations."""
    r = session.execute(text("""
        SELECT
          count(*) FILTER (WHERE co.eudr_covered) covered,
          count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination = 'deforestation_free') deforestation_free,
          count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination = 'non_compliant') non_compliant,
          count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination = 'geolocation_incomplete') geolocation_incomplete,
          count(*) FILTER (WHERE co.eudr_covered AND p.eudr_determination IS NULL) not_determined,
          COALESCE(SUM(p.eudr_loss_ha), 0) loss_ha,
          count(DISTINCT co.name) FILTER (WHERE co.eudr_covered) commodities
        FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
        WHERE p.org_id = :o
    """), {"o": org_id}).mappings().first()
    covered = r["covered"] or 0
    df_free = r["deforestation_free"] or 0
    determined = df_free + (r["non_compliant"] or 0)
    pct_free = round(100.0 * df_free / determined, 1) if determined else None
    material = covered > 0
    return {
        "topic": "E4", "title": "Biodiversity & ecosystems — deforestation", "standard": "ESRS E4 (with EUDR)",
        "material": material,
        "eudr_covered_plots": covered, "eudr_commodities": r["commodities"],
        "deforestation_free": df_free, "non_compliant": r["non_compliant"],
        "geolocation_incomplete": r["geolocation_incomplete"], "not_determined": r["not_determined"],
        "deforestation_free_pct_of_determined": pct_free,
        "post_cutoff_forest_loss_ha": round(float(r["loss_ha"] or 0), 2),
        "basis": "Per-plot deforestation determination vs the 31-Dec-2020 EUDR cutoff (Hansen Global Forest Change). Only plots we actually determined are counted as deforestation-free — never assumed.",
    }


def build_esrs_pack(session: Session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                    material: int = MATERIAL) -> dict:
    """The Climate & Nature disclosure pack: E1 (physical) + E3 (water) + E4 (deforestation) + scope."""
    e1 = build_e1_report(session, org_id, scenario=scenario, horizon=horizon, material_threshold=material)
    climate = {
        "topic": "E1", "title": "Climate change — physical risk", "standard": "ESRS E1-9 — anticipated financial effects",
        "material": len(e1["material_hazards"]) > 0,
        "financial_effects": e1["financial_effects"],
        "material_hazards": [{"hazard": h["hazard"], "label": h["label"], "class": h["class"]} for h in e1["material_hazards"]],
        "detail_ref": "See the full CSRD · ESRS E1 report for the hazard-by-hazard breakdown, projections and adaptation.",
    }
    return {
        "entity": e1["entity"],
        "pack": "Climate & Nature (ESRS E1 physical · E3 · E4)",
        "reporting_basis": e1["reporting_basis"],
        "topics": [climate, water_topic(session, org_id, threshold=material), biodiversity_topic(session, org_id)],
        "out_of_scope": OUT_OF_SCOPE,
        "provenance": e1["provenance"],
        "note": "This pack covers only the ESRS topics driven by our physical-climate + deforestation engine. "
                "GHG accounting, pollution, circular economy, social and governance are produced by your other tools "
                "and combined into one CSRD statement. A euro is a firm figure only where the hazard→yield/asset chain "
                "is validated; otherwise exposure is mapped and the € withheld.",
    }
