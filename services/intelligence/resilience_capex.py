"""Property resilience capex — "what do I spend, what loss do I avoid" for a real-estate book, on the owner's own
stated method (E69).

For each scored property:
  * physical loss   = value × its discount for physical risk (its override, else the stated valuation haircut for its
                      headline peril and band — ml.scoring.valuation_discount, method.valuation_haircut);
  * avoided loss    = physical loss × the owner's stated adaptation effectiveness for that peril
                      (method.adaptation_effectiveness);
  * resilience capex = value × the owner's stated retrofit capex share for the property's hazard band
                      (method.resilience_capex_share);
  * benefit-cost ratio = avoided loss ÷ capex; a retrofit is worth doing when it is at least one.
Measures are suggested from services.intelligence.adaptation. Whether the spend is EU-Taxonomy adaptation-aligned capex
is decided by the Taxonomy criteria, not here. A missing statement makes the plan a named gap.
"""
from __future__ import annotations

from collections import defaultdict

from ml.scoring.damage_function import band
from ml.scoring.valuation_discount import effective_haircut
from services.intelligence.adaptation import actions_for


def _property_resilience(method, prop: dict) -> dict | None:
    value = prop.get("property_value_eur") or prop.get("value_eur") or 0
    score, hazard = prop.get("headline_score"), prop.get("headline_hazard")
    if not value or score is None or hazard is None:
        return None
    b = band(score)
    haircut = effective_haircut(method, prop)
    eff = method.per_peril("method.adaptation_effectiveness", hazard)
    share = method.get("method.resilience_capex_share", b)
    if haircut is None or eff is None or share is None:
        return {"incomplete": True}
    physical, capex = value * haircut, value * share
    avoided = physical * eff
    bcr = round(avoided / capex, 2) if capex else None
    return {
        "property_id": prop.get("property_id") or prop.get("entity_id"),
        "name": prop.get("property_name") or prop.get("entity_name"),
        "headline_hazard": hazard, "headline_bucket": b, "headline_score": score,
        "physical_loss_eur": round(physical), "avoided_loss_eur": round(avoided), "resilience_capex_eur": round(capex),
        "adaptation_effectiveness_pct": round(100 * eff, 1), "benefit_cost_ratio": bcr,
        "worth_retrofit": bool(bcr is not None and bcr >= 1),
    }


def resilience_capex_plan(method, properties: list[dict]) -> dict:
    """The portfolio adaptation plan — total resilience capex, avoided loss, benefit-cost ratio and the per-property
    detail — or a gap naming what the owner has not stated."""
    rows = [r for r in (_property_resilience(method, p) for p in properties) if r]
    if not rows:
        return {"available": False, "reason": "no_scored_properties"}
    if any(r.get("incomplete") for r in rows):
        return {"available": False, "reason": "gap", "gap": method.gap_text()}
    total_capex = sum(r["resilience_capex_eur"] for r in rows)
    total_avoided = sum(r["avoided_loss_eur"] for r in rows)
    worth = [r for r in rows if r["worth_retrofit"]]
    by_hazard: dict = defaultdict(lambda: {"capex": 0.0, "avoided": 0.0, "n": 0})
    for r in rows:
        g = by_hazard[r["headline_hazard"]]
        g["capex"] += r["resilience_capex_eur"]
        g["avoided"] += r["avoided_loss_eur"]
        g["n"] += 1
    rows.sort(key=lambda r: -(r["benefit_cost_ratio"] or 0))
    return {
        "available": True, "n_properties": len(rows),
        "total_resilience_capex_eur": round(total_capex), "total_avoided_loss_eur": round(total_avoided),
        "total_physical_loss_eur": round(sum(r["physical_loss_eur"] for r in rows)),
        "portfolio_benefit_cost_ratio": round(total_avoided / total_capex, 2) if total_capex else None,
        "n_worth_retrofit": len(worth), "worth_retrofit_capex_eur": round(sum(r["resilience_capex_eur"] for r in worth)),
        "by_hazard": sorted([{"hazard": k, "resilience_capex_eur": round(v["capex"]), "avoided_loss_eur": round(v["avoided"]),
                              "n": v["n"]} for k, v in by_hazard.items()], key=lambda x: -x["avoided_loss_eur"]),
        "recommended_measures": actions_for(sorted(by_hazard))[:6],
        "top_properties": rows[:8],
        "method": ("Physical loss = value × the owner's discount for physical risk; avoided loss = that × the owner's "
                   "stated adaptation effectiveness for the peril; resilience capex = value × the owner's stated retrofit "
                   "capex share for the hazard band (method parameters, attested)."),
    }
