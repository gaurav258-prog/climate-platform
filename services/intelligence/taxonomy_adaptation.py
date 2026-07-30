"""EU Taxonomy — Climate change adaptation (Objective 2), the part our engine owns.

Full Art. 8 disclosure is % of turnover / capex / opex that is Taxonomy-eligible and -aligned across
six objectives — most of that is financial tagging + DNSH + minimum-safeguards, which live in the
customer's reporting suite. But the ADAPTATION objective turns on one hard, mandated input we produce:
a robust **Climate Risk & Vulnerability Assessment (CRVA)** of the assets, and evidence that adaptation
solutions address the material physical risks identified. That is exactly our own-operations physical
risk + adaptation layer.

So this assembles the **substantial-contribution evidence for the climate-adaptation objective** — CRVA
coverage, the asset value materially exposed (needing adaptation), and whether adaptation solutions are
identified — NOT the full eligible/aligned turnover-capex-opex tables. We say which is which.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from services.intelligence.company_sites import list_sites_with_risk
from services.intelligence.adaptation import actions_for

MATERIAL = 40


def adaptation_kpi(session: Session, org_id: str) -> dict:
    """Own-operations CRVA + climate-adaptation substantial-contribution evidence."""
    sites = list_sites_with_risk(session, org_id)
    located = [s for s in sites if s.get("lat") is not None]
    total_value = sum((s.get("value_eur") or 0) for s in located)
    exposed = [s for s in located if (s.get("hazard_score") or 0) >= MATERIAL]
    exposed_value = sum((s.get("value_eur") or 0) for s in exposed)
    exposed_hazards = sorted({s["top_hazard"] for s in exposed if s.get("top_hazard")})

    pct = lambda part, whole: round(100.0 * part / whole, 1) if whole else None
    return {
        "objective": "Climate change adaptation (EU Taxonomy Objective 2)",
        "crva": {
            "sites_total": len(sites), "sites_assessed": len(located),
            "coverage_pct": pct(len(located), len(sites)),
            "asset_value_assessed_eur": round(total_value),
        },
        "physical_risk": {
            "sites_materially_exposed": len(exposed),
            "asset_value_exposed_eur": round(exposed_value),
            "share_of_assets_exposed_pct": pct(exposed_value, total_value),
            "hazards": exposed_hazards,
        },
        # substantial-contribution to adaptation needs adaptation solutions addressing the identified risks;
        # we supply reference measures for every material hazard, so the exposed base has solutions IDENTIFIED
        # (identified, not certified as implemented — an honest distinction).
        "substantial_contribution": {
            "adaptation_solutions_identified": len(exposed) > 0,
            "measures": actions_for(exposed_hazards),
            "candidate_contributing_value_eur": round(exposed_value),
        },
        "out_of_scope": {
            "note": "This is the CRVA + substantial-contribution evidence for the climate-adaptation objective. "
                    "The full Art. 8 disclosure — the % of turnover / capex / opex that is Taxonomy-eligible and "
                    "-aligned — additionally requires DNSH, minimum safeguards, and financial (capex/opex) tagging, "
                    "which are produced in your reporting suite. We do not compute an aligned turnover/capex/opex %.",
            "we_provide": ["Climate Risk & Vulnerability Assessment (CRVA)", "material physical hazards per asset",
                           "adaptation solutions per hazard", "asset value exposed"],
            "you_provide": ["capex/opex tagged to adaptation", "DNSH assessment", "minimum-safeguards check",
                            "turnover/capex/opex eligible & aligned %"],
        },
    }
