"""Transition risk of a counterparty or issuer — the shift to a low-carbon economy, on the institution's stated method.

Facts and method are kept apart (E69):

  * FACTS — the counterparty's scope 1+2 emissions (reported, or the flagged EXIOBASE sector estimate), its revenue and
    its NACE division. Carbon intensity = (scope 1 + scope 2) / revenue in € million is arithmetic on them.
  * METHOD — the carbon price under a scenario and horizon (method.carbon_price, EUR per tCO2e — e.g. from the NGFS
    vintage the institution uses) and the share of the counterparty's value at risk of stranding
    (method.stranded_share, per NACE division under a scenario and horizon). Both are the institution's own statement
    for the financial year, attested by a second person; the platform supplies no default.

  carbon cost          = (scope 1 + scope 2) × stated carbon price            (in EUR, then in the revenue's currency)
  carbon cost share    = carbon cost / revenue
  transition score     = 100 × the larger of the carbon cost share and the stated stranded share, capped at 100 —
                         the share of the counterparty's economics the transition takes, in per cent (a definition,
                         not a fitted scale). Bucketed by the one shared score_to_bucket.

The carbon channel needs both scope 1 and scope 2 stated, and revenue: a scope not stated is never read as 0 (E76/E79).
Without them the carbon channel is absent, so the score is not given (the stranded share still is) and
'emissions_missing' names what the counterparty does not state; a method parameter not stated is a named gap. Computed at read time for the reading organisation — never stored across organisations.
"""
from __future__ import annotations

from typing import Optional

from core.types import score_to_bucket

MODEL_VERSION = "transition-v3-stated"
PER_MILLION = 1_000_000          # carbon intensity is reported in tCO2e per € million of revenue


def transition_block(method, scope1_tco2e: Optional[float], scope2_tco2e: Optional[float],
                     revenue: Optional[float], division: Optional[str], scenario: str, horizon: str,
                     eur_per_unit: float = 1.0) -> dict:
    """One counterparty × scenario × horizon. `revenue` is in the book's currency; eur_per_unit converts it to EUR (the
    unit the carbon price is stated in). Every figure that needs a missing input is None, and 'gap' names it."""
    missing = [n for n, v in (("scope 1", scope1_tco2e), ("scope 2", scope2_tco2e), ("revenue", revenue)) if v is None]
    if revenue is not None and revenue <= 0:
        missing.append("revenue above 0")
    have_emissions = not missing
    tonnes = scope1_tco2e + scope2_tco2e if have_emissions else None
    gaps = []

    stranded = method.per_division("method.stranded_share", division or "any", scenario, horizon)
    if stranded is None:
        gaps.append(f"method.stranded_share ({division or 'any'}@{scenario}/{horizon})")

    intensity = cost_share = cost = price = None
    if have_emissions:
        revenue_eur = revenue * eur_per_unit
        intensity = round(tonnes / (revenue_eur / PER_MILLION), 2)
        price = method.get("method.carbon_price", f"{scenario}/{horizon}")
        if price is None:
            gaps.append(f"method.carbon_price ({scenario}/{horizon})")
        else:
            cost_share = tonnes * price / revenue_eur
            cost = cost_share * revenue                       # in the revenue's currency

    score = None
    if have_emissions and cost_share is not None and stranded is not None:
        score = round(min(100.0, 100 * max(cost_share, stranded)), 1)
    return {
        "transition_risk_score": score,
        "risk_bucket": score_to_bucket(score).value if score is not None else None,
        "carbon_intensity_tco2e_per_meur": intensity,
        "stranded_asset_pct": round(100 * stranded, 2) if stranded is not None else None,
        "carbon_price_eur_per_tonne": price,
        "carbon_price_impact": round(cost, 2) if cost is not None else None,
        "carbon_cost_pct_of_revenue": round(100 * cost_share, 2) if cost_share is not None else None,
        "dominant_channel": (None if score is None else "carbon_cost" if cost_share >= stranded else "stranded_asset"),
        "has_emissions": have_emissions,
        "emissions_missing": missing or None,          # the counterparty's facts not stated (data, not method)
        "model_version": MODEL_VERSION,
        **({"gap": "not stated: " + ", ".join(gaps)} if gaps else {}),
    }
