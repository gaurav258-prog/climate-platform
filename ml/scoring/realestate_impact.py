"""Real estate's operating-income drag: what insuring a property against its physical-climate hazards would cost its
owner, as a share of the property's net operating income.

The cost is the technical premium of ml.scoring.insurance_pricing — every insured peril at the location, on the
owner's stated method (damage ratios, event probabilities, loadings; services.money.params) — on the property's
INSURED VALUE (the schedule's sum_insured_eur, the owner's own figure; market value is not a sum insured). Without the
insured value, or an input of the method, the drag is a named gap (E69).
"""
from __future__ import annotations

from ml.scoring.insurance_pricing import price_perils


def noi_impact(method, hazards: list[dict], sum_insured_eur: float | None, annual_noi_eur: float | None) -> dict:
    """{technical_premium_eur, expected_annual_loss_eur, noi_impact_pct, perils, gap?} — None where not computable."""
    if not sum_insured_eur:
        return {"technical_premium_eur": None, "expected_annual_loss_eur": None, "noi_impact_pct": None,
                "gap": "the property's insured value (sum_insured_eur) is not in the schedule"}
    pricing = price_perils(method, hazards, sum_insured_eur)
    if pricing is None:
        return {"technical_premium_eur": 0.0, "expected_annual_loss_eur": 0.0, "noi_impact_pct": 0.0 if annual_noi_eur else None,
                "note": "no insured peril is scored at the location"}
    prem = pricing.get("technical_premium_eur")
    return {**pricing, "noi_impact_pct": round(100 * prem / annual_noi_eur, 2) if prem is not None and annual_noi_eur else None}
