"""Property resilience-capex — the "what do I spend, what loss do I avoid" layer for a real-estate book.

The physical engine tells a REIT the climate loss on each property. It did not answer the operator's actual
question: is it worth retrofitting, and how much of that spend is EU-Taxonomy adaptation-aligned capex?

For each property this pairs three quantities:
  * the modelled physical loss (value × the continuous haircut on the property's headline score) — computed;
  * the AVOIDED loss = that physical loss × a disclosed per-hazard adaptation EFFECTIVENESS (the fraction of
    loss a full resilience retrofit is expected to prevent — reference ranges from EU Climate-ADAPT / IPCC AR6
    WGII, not a fitted per-asset figure);
  * the resilience CAPEX = a disclosed reference fraction of asset value by hazard severity (illustrative
    retrofit cost tiers, the same "disclosed relative tier" standard as the damage schedule).
From those it derives the benefit-cost ratio, whether a retrofit clears BCR ≥ 1, and the recommended measures
(reused from services.intelligence.adaptation). The whole retrofit qualifies as EU-Taxonomy climate-change-
adaptation-aligned capex (Objective 2), surfaced as such. Both the effectiveness and the capex tiers are
disclosed reference assumptions, never presented as a fitted per-property quote.
"""
from __future__ import annotations

from collections import defaultdict

from ml.scoring.damage_function import collateral_haircut_pct
from services.intelligence.adaptation import actions_for

# Fraction of the modelled physical loss a full resilience retrofit is expected to avoid, by hazard.
# Disclosed reference effectiveness (EU Climate-ADAPT / IPCC AR6 WGII adaptation ranges).
ADAPTATION_EFFECTIVENESS = {
    "flood": 0.45, "coastal_flood": 0.40, "storm": 0.40, "wildfire": 0.50, "seismic": 0.50,
    "volcanic": 0.20, "heat_chronic": 0.35, "heat_acute": 0.35, "drought": 0.25, "soil_water": 0.30,
    "pollution": 0.30,
}
_DEFAULT_EFFECTIVENESS = 0.30

# Reference resilience-retrofit capex as a % of asset value, by headline severity bucket. Illustrative
# reference tiers (property-resilience literature ranges), disclosed like the damage-schedule tiers.
RESILIENCE_CAPEX_PCT = {"VH": 4.0, "H": 2.5, "M": 1.0, "L": 0.3}


def _property_resilience(prop: dict, severity_model: str) -> dict | None:
    value = prop.get("property_value_eur") or prop.get("value_eur") or 0
    score = prop.get("headline_score")
    bucket = prop.get("headline_bucket")
    hazard = prop.get("headline_hazard")
    if not value or not bucket or score is None:
        return None
    attrs = {"construction_type": prop.get("construction_type"), "year_built": prop.get("year_built"),
             "number_of_stories": prop.get("number_of_stories")}
    sm = (prop.get("valuation") or {}).get("severity_model") or severity_model
    haircut = collateral_haircut_pct(score, bucket, hazard, sm, attrs) / 100.0
    physical_loss = value * haircut
    effectiveness = ADAPTATION_EFFECTIVENESS.get(hazard, _DEFAULT_EFFECTIVENESS)
    avoided = physical_loss * effectiveness
    capex = value * RESILIENCE_CAPEX_PCT.get(bucket, 0.3) / 100.0
    bcr = round(avoided / capex, 2) if capex else None
    return {
        "property_id": prop.get("property_id") or prop.get("entity_id"),
        "name": prop.get("property_name") or prop.get("entity_name"),
        "headline_hazard": hazard, "headline_bucket": bucket, "headline_score": score,
        "physical_loss_eur": round(physical_loss),
        "avoided_loss_eur": round(avoided),
        "resilience_capex_eur": round(capex),
        "adaptation_effectiveness_pct": round(effectiveness * 100, 1),
        "benefit_cost_ratio": bcr,
        "worth_retrofit": bool(bcr and bcr >= 1.0),
    }


def resilience_capex_plan(properties: list[dict], severity_model: str = "universal") -> dict:
    """properties: the REIT property book. Returns the portfolio adaptation plan — total resilience capex,
    avoided loss, benefit-cost ratio, EU-Taxonomy adaptation-aligned capex, and the per-property detail."""
    rows = [r for r in (_property_resilience(p, severity_model) for p in properties) if r]
    if not rows:
        return {"available": False, "reason": "no_scored_properties"}

    total_capex = sum(r["resilience_capex_eur"] for r in rows)
    total_avoided = sum(r["avoided_loss_eur"] for r in rows)
    total_physical = sum(r["physical_loss_eur"] for r in rows)
    worth = [r for r in rows if r["worth_retrofit"]]

    by_hazard: dict = defaultdict(lambda: {"capex": 0.0, "avoided": 0.0, "n": 0})
    hazards_present: set = set()
    for r in rows:
        h = r["headline_hazard"] or "unknown"
        hazards_present.add(r["headline_hazard"])
        by_hazard[h]["capex"] += r["resilience_capex_eur"]
        by_hazard[h]["avoided"] += r["avoided_loss_eur"]
        by_hazard[h]["n"] += 1

    rows.sort(key=lambda r: -(r["benefit_cost_ratio"] or 0))
    return {
        "available": True,
        "n_properties": len(rows),
        "total_resilience_capex_eur": round(total_capex),
        "total_avoided_loss_eur": round(total_avoided),
        "total_physical_loss_eur": round(total_physical),
        "portfolio_benefit_cost_ratio": round(total_avoided / total_capex, 2) if total_capex else None,
        "n_worth_retrofit": len(worth),
        "worth_retrofit_capex_eur": round(sum(r["resilience_capex_eur"] for r in worth)),
        # the whole resilience retrofit qualifies as EU-Taxonomy climate-adaptation-aligned capex (Objective 2)
        "taxonomy_adaptation_aligned_capex_eur": round(total_capex),
        "by_hazard": sorted(
            [{"hazard": k, "resilience_capex_eur": round(v["capex"]), "avoided_loss_eur": round(v["avoided"]),
              "n": v["n"]} for k, v in by_hazard.items()], key=lambda x: -x["avoided_loss_eur"]),
        "recommended_measures": actions_for([h for h in hazards_present if h])[:6],
        "top_properties": rows[:8],
        "method": ("Avoided loss = modelled physical loss × a disclosed per-hazard adaptation effectiveness "
                   "(EU Climate-ADAPT / IPCC AR6 WGII ranges). Resilience capex = a disclosed reference fraction "
                   "of asset value by severity. Both are disclosed relative tiers, not a fitted per-property "
                   "quote; the retrofit is EU-Taxonomy climate-adaptation-aligned capex (Objective 2)."),
    }
