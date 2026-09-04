"""ESRS Climate & Nature disclosure pack — the topics our golden source genuinely supports.

CSRD/ESRS is one statement, but only some of it is *ours*: the topics that run off the satellite +
hazard + per-plot-geolocation + deforestation engine. This assembles those into one pack —
  E1  Climate change · physical risk   (reuses services.intelligence.csrd_e1)
  E3  Water                            (water-stress / soil-water exposure of sites & sourcing)
  E4  Biodiversity & ecosystems        (deforestation from EUDR determinations + protected-area overlap)
— and is explicit about what it does NOT cover (GHG accounting, pollution, circular economy, social,
governance), which belong to the customer's carbon / HR tooling. See docs/AGRI_REGULATORY_SCOPE.md.

Honesty carries through: a euro is a firm figure only where the chain is validated; deforestation is
reported only where we actually determined it (never a green we didn't earn).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.csrd_e1 import build_e1_report
from services.intelligence.protected_area import protected_area_exposure

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
        "metric_kind": "water_stress_proxy",
        "own_operations": {"sites": sites["n"], "sites_water_stressed": sites["exposed"], "asset_value_exposed_eur": float(sites["value_exposed"] or 0)},
        "upstream": {"plots": plots["n"], "plots_water_stressed": plots["exposed"], "spend_exposed_eur": float(plots["spend_exposed"] or 0), "peak_score": float(plots["peak"]) if plots["peak"] is not None else None},
        "basis": f"Worst standing water hazard (water stress / soil-water deficit) per site & plot, Copernicus/ECMWF-indexed; 'exposed' = score ≥ {threshold}.",
        "e3_4_note": "ESRS E3-4 mandates METERED water consumption (m³) and intensity (m³ per €m net revenue). "
                     "This is a water-STRESS exposure proxy (hazard-based site risk), NOT the metered figure — "
                     "report metered m³ from your site meters; use this to target metering and disclose water-risk context.",
    }


def biodiversity_topic(session: Session, org_id: str) -> dict:
    """ESRS E4 — biodiversity & ecosystems: deforestation across the sourcing book (from the EUDR satellite
    determinations) AND own sites / sourcing plots that sit in or near a protected area (E4-5, from the
    `protected_h3_cell` overlap engine). Protected-area coverage grows as datasets land — no code change."""
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

    pa = protected_area_exposure(session, org_id)
    pa_assets = pa["sites"]["in_protected"] + pa["plots"]["in_protected"]
    material = covered > 0 or pa_assets > 0
    return {
        "topic": "E4", "title": "Biodiversity & ecosystems", "standard": "ESRS E4 (with EUDR)",
        "material": material,
        "eudr_covered_plots": covered, "eudr_commodities": r["commodities"],
        "deforestation_free": df_free, "non_compliant": r["non_compliant"],
        "geolocation_incomplete": r["geolocation_incomplete"], "not_determined": r["not_determined"],
        "deforestation_free_pct_of_determined": pct_free,
        "post_cutoff_forest_loss_ha": round(float(r["loss_ha"] or 0), 2),
        "basis": "Per-plot deforestation determination vs the 31-Dec-2020 EUDR cutoff (Hansen Global Forest Change). Only plots we actually determined are counted as deforestation-free — never assumed.",
        "protected_areas": {
            "sites_in_protected": pa["sites"]["in_protected"], "sites_total": pa["sites"]["total"],
            "site_value_in_protected_eur": round(pa["sites"]["value_in_eur"], 2),
            "plots_in_protected": pa["plots"]["in_protected"], "plots_total": pa["plots"]["total"],
            "plot_spend_in_protected_eur": round(pa["plots"]["spend_in_eur"], 2),
            "coverage": _protected_area_coverage(pa["datasets"]),
            "basis": "ESRS E4-5 — own sites and sourcing plots whose H3 cell falls in (or within the loaded "
                     "buffer of) a designated protected area, by indexed membership against the protected-area "
                     "overlap engine. Overlap is reported only for the areas actually loaded; non-covered "
                     "geographies are disclosed as coverage gaps, never as 'no overlap'.",
        },
    }


# Protected-area datasets → (label, geographic coverage) for honest disclosure of the overlap's reach.
_PA_DATASET_LABELS = {
    "natura2000": ("Natura 2000", "EU-27 (EEA designated sites)"),
    "wdpa": ("WDPA", "Global (World Database on Protected Areas)"),
    "wdoecm": ("WD-OECM", "Global (other effective area-based conservation measures)"),
    "kba": ("Key Biodiversity Areas", "Global (KBA network)"),
    "osm": ("OpenStreetMap protected areas", "Global where mapped (community)"),
}


def _protected_area_coverage(datasets: dict) -> dict:
    """Say plainly which protected-area layers back the overlap and which authoritative global layer is not
    yet loaded — so a 'no overlap' outside the EU is never mistaken for a clean result."""
    loaded = [{"dataset": k, "label": _PA_DATASET_LABELS.get(k, (k, "—"))[0],
               "geography": _PA_DATASET_LABELS.get(k, (k, "—"))[1], "cells": v}
              for k, v in sorted(datasets.items())]
    has_wdpa = "wdpa" in datasets
    return {
        "loaded": loaded,
        "authoritative_global_loaded": has_wdpa,
        "note": ("Backed by the WDPA global layer." if has_wdpa else
                 "EU protected areas (Natura 2000) are loaded; the authoritative global layer (WDPA) is "
                 "wired-ready but pending its commercial data licence (IBAT) — until it is loaded, "
                 "protected-area overlap outside the EU is a disclosed coverage gap, not a determination."),
    }


def build_esrs_pack(session: Session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                    material: int = MATERIAL) -> dict:
    """The Climate & Nature disclosure pack: E1 (physical) + E3 (water) + E4 (deforestation + protected areas) + scope."""
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
