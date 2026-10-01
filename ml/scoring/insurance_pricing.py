"""Insured loss and technical premium from a location's hazard, on the institution's own stated method (E69).

For each insured peril at a location (data/reference/declarations/insurance_property_perils.json):

  scenario loss          sum insured × the stated damage ratio for the peril and the band of its score
                         (method.damage_ratio) — the loss if a damaging event occurs
  net scenario loss      less the policy's deductible (a share of the sum insured, the policy's own field)
  expected annual loss   net scenario loss × the stated annual probability of a damaging event for the peril and band
                         (method.annual_event_probability); its return period is 1 / that probability
  technical premium      expected annual loss ÷ (1 − the stated expense ratio − the stated profit margin): the
                         Casualty Actuarial Society's loss-cost-multiplier form (Statement of Principles Regarding P&C
                         Ratemaking); it is a modelled premium, not the premium written (that is the book's)

Every input that is not the policy's own field is the institution's statement (services.money.params). A missing one
makes the figure None and names the gap — the hazard score is validated as a ranking only, so no share is derived
from it by a platform schedule.
"""
from __future__ import annotations

from ml.scoring.damage_function import band, damage_ratio, event_probability


def price_policy(method, risk_score: float, sum_insured_eur: float, deductible_pct: float = 0.0,
                 hazard: str | None = None) -> dict:
    """One peril at one location: the chain above, each step None once an input is not stated."""
    b = band(risk_score)
    mdr = damage_ratio(method, hazard, risk_score)
    prob = event_probability(method, hazard, risk_score)
    scenario = None if mdr is None else sum_insured_eur * mdr
    retained = sum_insured_eur * max(0.0, deductible_pct or 0.0)
    net = None if scenario is None else max(0.0, scenario - retained)
    eal = None if net is None or prob is None else net * prob
    return {
        "risk_bucket": b, "mdr": mdr, "annual_occurrence_prob": prob,
        "return_period_years": round(1 / prob, 1) if prob else None,
        "scenario_loss_eur": None if scenario is None else round(scenario, 2),
        "retained_loss_eur": round(retained, 2),
        "net_scenario_loss_eur": None if net is None else round(net, 2),
        "expected_annual_loss_eur": None if eal is None else round(eal, 2),
    }


def technical_premium(method, eal: float | None, sum_insured_eur: float) -> dict:
    """{technical_premium_eur, rate_on_line_pct} from an expected annual loss and the stated loadings (None: a gap)."""
    exp, prof = method.get("method.expense_ratio"), method.get("method.profit_margin")
    if eal is None or exp is None or prof is None or exp + prof >= 1:
        return {"technical_premium_eur": None, "rate_on_line_pct": None}
    prem = eal / (1 - exp - prof)
    return {"technical_premium_eur": round(prem, 2),
            "rate_on_line_pct": round(100 * prem / sum_insured_eur, 3) if sum_insured_eur else None}


def _perils() -> dict:
    import json
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "data" / "reference" / "declarations" / "insurance_property_perils.json"
    return json.loads(f.read_text())["perils"]


def insured_peril(hazard: str | None, model_version: str | None = None) -> bool:
    """A hazard priced as property damage: listed as an insured peril, and scored on a likelihood / intensity scale for
    buildings under this model (a susceptibility class is not an occurrence probability — core.hazard_relevance)."""
    from core.hazard_relevance import is_headline_eligible
    return bool(hazard) and bool((_perils().get(hazard) or {}).get("insured")) and is_headline_eligible(hazard, model_version=model_version)


def price_perils(method, hazards: list[dict], sum_insured_eur: float, deductible_pct: float = 0.0) -> dict | None:
    """A policy priced peril by peril: each insured peril at the location on its own score, damage ratio and event
    probability, the deductible applying per occurrence; the policy's expected annual loss and technical premium are
    their sum. `perils` carries each component for the catastrophe accumulation. The headline fields are those of the
    peril with the largest scenario loss. None when no insured peril is scored at the location; the figures are None
    (with `gap`) when a peril's method is not stated — never a partial sum."""
    comps = []
    for h in hazards or []:
        score = h.get("score")
        if score is None or score <= 0 or not insured_peril(h.get("hazard"), h.get("model_version")):
            continue
        p = price_policy(method, float(score), sum_insured_eur, deductible_pct, hazard=h["hazard"])
        comps.append({"hazard": h["hazard"], "score": round(float(score), 1), **p})
    if not comps:
        return None
    complete = all(c["expected_annual_loss_eur"] is not None for c in comps)
    eal = round(sum(c["expected_annual_loss_eur"] for c in comps), 2) if complete else None
    driver = max(comps, key=lambda c: c["scenario_loss_eur"] if c["scenario_loss_eur"] is not None else -1.0)
    return {**{k: driver[k] for k in ("mdr", "scenario_loss_eur", "retained_loss_eur", "net_scenario_loss_eur",
                                      "return_period_years", "annual_occurrence_prob", "risk_bucket")},
            "driver_peril": driver["hazard"], "expected_annual_loss_eur": eal, "pure_premium_eur": eal,
            **technical_premium(method, eal, sum_insured_eur),
            **({} if complete else {"gap": method.gap_text()}),
            "perils": [{k: c[k] for k in ("hazard", "score", "mdr", "net_scenario_loss_eur", "annual_occurrence_prob",
                                          "return_period_years", "expected_annual_loss_eur", "risk_bucket")} for c in comps]}
