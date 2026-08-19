"""Transition-risk model — the climate risk from the shift to a low-carbon
economy, which is a property of an ISSUER/SECTOR, not a map cell (hence its own
golden surface `issuer_transition_scores`, not canonical_scores).

Same honesty standard as the physical side: a transparent method built on
NAMED, CITED anchors, with every simplification disclosed rather than a hidden
multiplier. This is a v1 indicator, not a fitted valuation model, and says so.

Two channels, combined by taking the DOMINANT one (no double-counting):

  1. Carbon-cost intensity — the earnings-at-risk channel.
       carbon_intensity = (scope1 + scope2 tCO2e) / revenue_€m           [standard WACI building block]
       annual_carbon_cost = (scope1 + scope2) × scenario_carbon_price     [€ at the scenario's price]
       carbon_cost_ratio  = annual_carbon_cost / revenue                  [fraction of revenue consumed]
     Carbon prices come from the NGFS scenario carbon-price trajectories
     (Network for Greening the Financial System, Phase IV, global average,
     REMIND/GCAM marker models) — representative published values, used as
     disclosed illustrative anchors, NOT fitted per issuer:
       - Net Zero 2050 (our 'orderly_1_5c'): steep early price
       - Delayed / Disorderly ('disorderly_2c'): low to 2030 then sharp
       - Current Policies ('hot_house_3_5c'): stays low — transition risk is
         small precisely because little transition happens (the risk is physical)
       - baseline / 'current': today's limited global carbon pricing (~€5),
         with a note that EU-ETS-covered emissions face a much higher real price.

  2. Stranded-asset exposure — the obsolescence channel, by sector.
       sector_base_stranded × scenario_ambition_factor
     Sector base tiers are keyed to NACE divisions where the transition story is
     well established (fossil extraction, refining, fossil power, heavy
     industry, ICE autos). Disclosed relative tiers, not fitted asset-level
     stranding — same standard as the physical peril tiers.

score = min(100, max(carbon_cost_score, stranded_score)). Bucketed by the one
shared score_to_bucket. Every output carries model_version so it is reproducible
and supersedable exactly like a physical score.
"""
from __future__ import annotations

from typing import Optional

from core.types import score_to_bucket

MODEL_VERSION = "transition-v1-ngfs"

# NGFS-anchored carbon price by scenario and horizon, in EUR per tonne CO2e.
# Representative global-average values from the NGFS Phase IV scenarios —
# disclosed illustrative anchors, not fitted. See module docstring.
CARBON_PRICE_EUR = {
    "baseline":        {"current": 5,   "2030": 10,  "2050": 15,  "2100": 20},
    "orderly_1_5c":    {"current": 5,   "2030": 130, "2050": 250, "2100": 600},   # Net Zero 2050: steep, early
    "disorderly_2c":   {"current": 5,   "2030": 40,  "2050": 340, "2100": 600},   # Delayed: low then sharp
    "hot_house_3_5c":  {"current": 5,   "2030": 10,  "2050": 15,  "2100": 25},    # Current Policies: stays low
}

# Scenario ambition factor applied to sector stranding (more ambitious transition
# strands high-carbon assets faster). Hot-house strands little; net-zero the most.
SCENARIO_STRAND_FACTOR = {
    "baseline": 0.10, "orderly_1_5c": 1.00, "disorderly_2c": 0.85, "hot_house_3_5c": 0.15,
}
HORIZON_STRAND_FACTOR = {"current": 0.15, "2030": 0.45, "2050": 1.00, "2100": 1.10}

# Base stranded-asset fraction by NACE division (2-digit prefix) — disclosed
# relative tiers for sectors with an established transition/stranding thesis.
NACE_STRANDED_BASE = {
    "05": 0.45,  # mining of coal and lignite
    "06": 0.40,  # extraction of crude petroleum and natural gas
    "19": 0.35,  # manufacture of coke and refined petroleum products
    "35": 0.20,  # electricity, gas, steam (mix unknown here → a moderate tier)
    "24": 0.20,  # manufacture of basic metals (steel)
    "23": 0.18,  # manufacture of other non-metallic mineral products (cement)
    "29": 0.15,  # manufacture of motor vehicles (ICE exposure)
    "49": 0.10,  # land transport
    "51": 0.12,  # air transport
}

# Score-shaping constants (documented, monotonic).
CARBON_COST_AT_SCORE_90 = 0.30   # a 30%-of-revenue carbon cost maps to a 90 score
STRANDED_SCORE_WEIGHT = 60.0     # a 100%-stranded sector maps to a 60 score on the stranding channel alone


def _nace_division(nace_code: Optional[str]) -> Optional[str]:
    if not nace_code:
        return None
    return nace_code.strip()[:2]


def transition_score(
    scope1_tco2e: Optional[float], scope2_tco2e: Optional[float], scope3_tco2e: Optional[float],
    revenue_eur: Optional[float], nace_code: Optional[str], scenario: str, horizon: str,
) -> Optional[dict]:
    """One issuer × scenario × horizon → transition-risk block, or None if the
    inputs to say anything honest are absent (no emissions AND no sector signal).
    Never fabricates a zero for a missing input."""
    price = CARBON_PRICE_EUR.get(scenario, {}).get(horizon)
    if price is None:
        return None

    s1 = scope1_tco2e or 0.0
    s2 = scope2_tco2e or 0.0
    have_emissions = (scope1_tco2e is not None or scope2_tco2e is not None) and bool(revenue_eur)

    # Channel 1: carbon-cost intensity
    carbon_intensity = None
    carbon_cost_eur = None
    carbon_cost_ratio = None
    carbon_score = 0.0
    if have_emissions and revenue_eur:
        revenue_meur = revenue_eur / 1e6
        carbon_intensity = round((s1 + s2) / revenue_meur, 2) if revenue_meur else None
        carbon_cost_eur = (s1 + s2) * price
        carbon_cost_ratio = carbon_cost_eur / revenue_eur if revenue_eur else 0.0
        carbon_score = min(90.0, (carbon_cost_ratio / CARBON_COST_AT_SCORE_90) * 90.0)

    # Channel 2: sector stranded-asset exposure. stranded_pct is a fraction (0-1);
    # a fully-stranded sector (stranded_pct=1) maps to STRANDED_SCORE_WEIGHT (=60).
    base = NACE_STRANDED_BASE.get(_nace_division(nace_code), 0.02)
    stranded_pct = base * SCENARIO_STRAND_FACTOR.get(scenario, 0.1) * HORIZON_STRAND_FACTOR.get(horizon, 0.15)
    stranded_score = min(100.0, stranded_pct * STRANDED_SCORE_WEIGHT)

    if not have_emissions and base <= 0.02:
        # nothing to say honestly — no emissions and a sector with no transition thesis
        return None

    score = round(min(100.0, max(carbon_score, stranded_score)), 1)
    return {
        "transition_risk_score": score,
        "risk_bucket": score_to_bucket(score).value,
        "carbon_intensity_tco2e_per_meur": carbon_intensity,
        "stranded_asset_pct": round(stranded_pct * 100, 2),
        "carbon_price_impact_eur": round(carbon_cost_eur, 2) if carbon_cost_eur is not None else None,
        "carbon_price_eur_per_tonne": price,
        "carbon_cost_pct_of_revenue": round(carbon_cost_ratio * 100, 2) if carbon_cost_ratio is not None else None,
        "dominant_channel": "carbon_cost" if carbon_score >= stranded_score else "stranded_asset",
        "model_version": MODEL_VERSION,
        "has_emissions": have_emissions,
    }
