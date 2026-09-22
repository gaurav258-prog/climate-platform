"""CSRD / ESRS E1 physical-risk report — the corporate disclosure twin of the SFDR statement.

Assembles the physical-climate-risk section a company in CSRD scope must disclose (ESRS E1-9:
anticipated financial effects from material physical risks), from data the platform already holds:
its OWN operational sites (asset value + throughput exposed) AND its upstream sourcing (COGS-at-risk),
scored on the golden source, with the acute/chronic split ESRS asks for, forward horizons, and the
adaptation measures for resilience. Honesty is preserved end-to-end: a euro is reported as a firm
'volume at risk' only where the hazard→yield chain is validated; otherwise exposure is mapped and the
euro withheld — the report says which is which.

This is NOT legal advice or a filing; it is a defensible, provenance-carried draft the company's
sustainability team completes and signs.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.intelligence.adaptation import actions_for
from services.intelligence.company_sites import bi_downtime_fraction, list_sites_with_risk

# ESRS E1 splits physical risk into ACUTE (event-driven) and CHRONIC (gradual). Seismic/pollution are
# not climate hazards → excluded from the E1 climate report (covered under other risk lenses). The
# climate-hazard scope lives in one shared module so E1 and the Taxonomy adaptation report can't
# diverge on whether an asset is materially exposed (audit T8).
from services.intelligence.hazard_scope import ACUTE, CHRONIC, CLIMATE
from services.intelligence.supply_cogs import project_org_supply

MATERIAL_THRESHOLD = 40  # a hazard is "material" for a location once its score reaches elevated

_LABELS = {"drought": "Drought", "soil_water": "Soil-water deficit", "heat_chronic": "Chronic heat",
           "heat_acute": "Acute heat / heatwave", "flood": "Flood", "storm": "Storm / wind",
           "wildfire": "Wildfire", "water_stress": "Water stress"}


def _class(h: str) -> str:
    return "acute" if h in ACUTE else "chronic" if h in CHRONIC else "other"


def build_e1_report(session: Session, org_id: str, scenario: str = "baseline", horizon: str = "current",
                    material_threshold: int = MATERIAL_THRESHOLD) -> dict:
    org = session.execute(text("SELECT name, type, country, eori FROM organizations WHERE org_id=:o"),
                          {"o": org_id}).mappings().first()

    # ── own operations: sites, each with worst climate hazard, asset value + BI exposure ──────────
    # Read own-ops on the SAME basis the report is labelled with, so a 2050 filing isn't silently
    # computed at baseline/current (audit T3) — matches the sourcing half below.
    sites = list_sites_with_risk(session, org_id, scenario=scenario, horizon=horizon)
    op_by_hazard: dict[str, dict] = {}
    op_asset_total = op_asset_at_risk = op_throughput = op_bi = 0.0
    # ESRS E1-9 para 66(b): the proportion of at-risk assets ADDRESSED by a disclosed adaptation action —
    # tracked alongside the € figures, keyed on whether the site's own top (driving) hazard has one.
    adaptation_covered_value = 0.0
    for s in sites:
        av, tp, hs, hz = (s.get("value_eur") or 0), (s.get("throughput_eur") or 0), s.get("hazard_score"), s.get("top_hazard")
        op_asset_total += av; op_throughput += tp
        if hz in CLIMATE and hs is not None and hs >= material_threshold:
            op_asset_at_risk += av
            bi = tp * bi_downtime_fraction(hs); op_bi += bi
            d = op_by_hazard.setdefault(hz, {"hazard": hz, "label": _LABELS.get(hz, hz), "class": _class(hz),
                                             "n_sites": 0, "asset_value_eur": 0.0, "bi_at_risk_eur": 0.0, "max_score": 0})
            d["n_sites"] += 1; d["asset_value_eur"] += av; d["bi_at_risk_eur"] += bi; d["max_score"] = max(d["max_score"], round(hs))
            if actions_for([hz]):   # a disclosed adaptation measure exists for this site's driving hazard
                adaptation_covered_value += av

    # ── upstream sourcing: COGS-at-risk by commodity (published) vs exposure-mapped (held) ────────
    r = project_org_supply(session, org_id, scenario=scenario, time_horizon=horizon)
    up_by_hazard: dict[str, dict] = {}
    cogs_published = mapped_exposure = 0.0
    commodities = []
    for c in r.commodities:
        hz, hs = c.top_hazard, c.avg_hazard
        pub = c.calibration in ("backtested", "ranged")
        var = (c.volume_at_risk_eur or 0) if pub else 0
        cogs_published += var
        if not pub:
            mapped_exposure += (c.annual_spend_eur or 0)
        commodities.append({"commodity": c.commodity, "hazard": hz, "avg_hazard": hs, "spend_eur": c.annual_spend_eur,
                            "published": pub, "volume_at_risk_eur": var if pub else None,
                            "volume_at_risk_low_eur": c.volume_at_risk_low_eur, "volume_at_risk_high_eur": c.volume_at_risk_high_eur,
                            "calibration": c.calibration, "fit_r2": c.fit_r2, "held_reason": c.held_reason,
                            # freeze the A–E Confidence Grade INTO the filing, not just the live UI (audit T5)
                            "confidence_grade": c.confidence_grade, "confidence_checks": c.confidence_checks})
        if hz in CLIMATE and hs is not None and hs >= material_threshold:
            d = up_by_hazard.setdefault(hz, {"hazard": hz, "label": _LABELS.get(hz, hz), "class": _class(hz),
                                             "n_commodities": 0, "spend_eur": 0.0, "cogs_at_risk_eur": 0.0, "max_score": 0})
            d["n_commodities"] += 1; d["spend_eur"] += (c.annual_spend_eur or 0)
            d["cogs_at_risk_eur"] += var; d["max_score"] = max(d["max_score"], round(hs))

    # ESRS E1-9 para 66(a)/(d): the € figures are also required as a PERCENTAGE of the same total the
    # numerator is drawn from — total own-ops asset value for assets, total own-ops throughput (the
    # platform's own-revenue proxy — see company_sites) for business interruption/net revenue. Both are
    # None (never a fabricated 0%) when the org has no own-ops total to divide by.
    pct_of_assets_at_risk = round(100.0 * op_asset_at_risk / op_asset_total, 1) if op_asset_total else None
    pct_of_revenue_at_risk = round(100.0 * op_bi / op_throughput, 1) if op_throughput else None
    adaptation_coverage_pct = round(100.0 * adaptation_covered_value / op_asset_at_risk, 1) if op_asset_at_risk else None

    material = sorted(set(op_by_hazard) | set(up_by_hazard),
                     key=lambda h: -max(op_by_hazard.get(h, {}).get("max_score", 0), up_by_hazard.get(h, {}).get("max_score", 0)))

    # ── forward horizons: material-hazard mean across the book's cells (own + sourcing) ───────────
    horizons = [dict(x) for x in session.execute(text("""
        SELECT hazard_type, time_horizon, ROUND(AVG(physical_risk_score)::numeric,1) avg_score
        FROM (
            SELECT v.hazard_type, v.time_horizon, v.physical_risk_score FROM v_sc_plot_physical_risk v
            JOIN sc_sourcing_plots p ON p.plot_id=v.plot_id WHERE p.org_id=:o AND v.scenario IN ('disorderly_2c','baseline')
            UNION ALL
            SELECT v.hazard_type, v.time_horizon, v.physical_risk_score FROM v_sc_site_physical_risk v WHERE v.org_id=:o AND v.scenario IN ('disorderly_2c','baseline')
        ) u WHERE hazard_type = ANY(:mat)
        GROUP BY hazard_type, time_horizon ORDER BY hazard_type, time_horizon
    """), {"o": org_id, "mat": list(material) or ['_none_']}).mappings().all()]

    return {
        "entity": {"name": org["name"] if org else None, "country": org["country"] if org else None,
                   "eori": org["eori"] if org else None},
        "standard": "ESRS E1 — Climate change (physical risk)", "datapoint": "E1-9 anticipated financial effects",
        "reporting_basis": {"scenario": scenario, "horizon": horizon},
        "material_hazards": [{"hazard": h, "label": _LABELS.get(h, h), "class": _class(h),
                              "own_operations": op_by_hazard.get(h), "upstream": up_by_hazard.get(h)} for h in material],
        "own_operations": {"n_sites": len(sites), "asset_value_eur": round(op_asset_total),
                           "asset_value_at_risk_eur": round(op_asset_at_risk), "throughput_eur": round(op_throughput),
                           "business_interruption_eur": round(op_bi), "by_hazard": list(op_by_hazard.values())},
        "upstream_sourcing": {"ingredient_spend_eur": round(r.ingredient_spend_eur), "cogs_at_risk_published_eur": round(cogs_published),
                              "exposure_mapped_spend_eur": round(mapped_exposure), "by_hazard": list(up_by_hazard.values()),
                              "commodities": commodities},
        "financial_effects": {
            "asset_value_at_risk_eur": round(op_asset_at_risk),
            "business_interruption_eur": round(op_bi),
            "cogs_at_risk_published_eur": round(cogs_published),
            "exposure_mapped_but_withheld_eur": round(mapped_exposure),
            # ESRS E1-9 para 66(a): monetary amount AND percentage of total (own-ops) assets at material
            # physical risk.
            "pct_of_assets_at_risk": pct_of_assets_at_risk,
            # ESRS E1-9 para 66(d): monetary amount AND percentage of net revenue (own-ops throughput,
            # our net-revenue proxy) at material physical risk.
            "pct_of_revenue_at_risk": pct_of_revenue_at_risk,
            # ESRS E1-9 para 66(b): proportion of at-risk assets addressed by a disclosed adaptation action.
            "adaptation_coverage_pct_of_at_risk_assets": adaptation_coverage_pct,
            "asset_value_at_risk_addressed_by_adaptation_eur": round(adaptation_covered_value),
            "note": "Business-interruption is a v0 illustrative estimate (throughput × expected downtime by hazard band). "
                    "COGS-at-risk is published only where the hazard→yield chain is validated (r² ≥ 0.40); other commodities' "
                    "exposure is mapped and the euro withheld. Percentages (ESRS E1-9 para 66(a)/(d)) are of the platform's "
                    "own-operations asset value / throughput; adaptation coverage (para 66(b)) is the share of AT-RISK asset "
                    "value whose site's driving hazard has a disclosed adaptation action (E1-3), not of total assets.",
        },
        "projections": horizons,
        "resilience": actions_for(material),
        "provenance": {
            "hazard_data": "Copernicus/ECMWF (ERA5, CMIP6) and NASA/USGS — direct authoritative feeds, indexed to H3 cells",
            "forest_data": "Hansen Global Forest Change (deforestation)",
            "yield_data": "FAOSTAT / Eurostat (crop calibration)",
            "publish_gate": "A euro is published only where a multi-year regression reproduces real crop failure (r² ≥ 0.40); "
                            "otherwise exposure is reported and the euro withheld.",
            "boundaries": "Country/land clipping via Natural Earth 1:50m.",
        },
    }
