"""
Real estate's "operating-income drag" — how much a property's physical-climate
risk costs its owner, expressed against NOI rather than a loan or a premium.

Deliberately NOT a new vulnerability model. "What would this property cost to
insure at this hazard exposure" IS the operating-income-drag question — the
same hazard-score -> scenario-loss -> annualized-loss -> premium chain already
built for insurance underwriting (ml/scoring/insurance_pricing.py's
Emanuel(2011)/CLIMADA-style sigmoid + CAS ratemaking) applies unchanged; this
module only re-expresses the resulting premium as a share of NOI, since an
owner's felt cost of physical risk is real-estate insurance getting more
expensive as much as it is direct damage.
"""
from __future__ import annotations

from ml.scoring.insurance_pricing import price_policy


def noi_impact(risk_score: float, property_value_eur: float, annual_noi_eur: float) -> dict:
    """Returns price_policy()'s full chain plus expected_insurance_premium_eur and
    noi_impact_pct (None, not 0, when annual_noi_eur is absent — honest absence,
    never a fabricated ratio, matching ml/scoring/valuation_discount.py's ltv_pct())."""
    pricing = price_policy(risk_score, property_value_eur)
    premium = pricing["gross_premium_eur"]
    return {
        **pricing,
        "expected_insurance_premium_eur": premium,
        "noi_impact_pct": round(100 * premium / annual_noi_eur, 2) if annual_noi_eur else None,
    }
