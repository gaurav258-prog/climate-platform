"""The money engines compute only on the institution's stated method (E69): every share, probability and loading is a
stated value read by peril and band (or the institution's 'any' value); anything not stated is a named gap and never
becomes a number — not in a sum, not as a zero. Pure: a Method built from given values, no database."""
from __future__ import annotations

from datetime import date

import pytest

from ml.scoring.cat_accumulation import catastrophe_accumulation
from ml.scoring.damage_function import band, damage_ratio, event_probability, valuation_haircut
from ml.scoring.insurance_pricing import (
    insured_peril,
    price_perils,
    price_policy,
    technical_premium,
)
from ml.scoring.realestate_impact import noi_impact
from ml.scoring.valuation_discount import (
    VAR_SIMULATIONS,
    monte_carlo_var,
    valuation_block,
    value_loss_band,
)
from services.intelligence.expected_loss import annual_expected_loss, lifetime_expected_loss
from services.intelligence.resilience_capex import resilience_capex_plan
from services.money.params import Method, at_risk
from services.scoring.combined_var import combined_climate_var

PE = date(2025, 12, 31)
FLOOD = {("method.valuation_haircut", "flood/H"): 0.15, ("method.valuation_haircut", "flood/VH"): 0.30,
         ("method.valuation_haircut", "any/M"): 0.05,
         ("method.damage_ratio", "flood/H"): 0.40, ("method.annual_event_probability", "flood/H"): 0.01,
         ("method.damage_ratio", "storm/M"): 0.10, ("method.annual_event_probability", "storm/M"): 0.02,
         ("method.expense_ratio", None): 0.25, ("method.profit_margin", None): 0.05, ("method.at_risk_level", None): 50,
         ("method.var_relative_uncertainty", None): 0.4}


def m(**extra):
    return Method.of({**FLOOD, **{(k.replace("__", "."), None): v for k, v in extra.items()}}, PE)


def test_the_core_reads_the_stated_value_for_the_peril_and_band_or_the_any_value():
    meth = m()
    assert band(60) == "H" and valuation_haircut(meth, "flood", 60) == 0.15 and valuation_haircut(meth, "flood", 80) == 0.30
    assert valuation_haircut(meth, "storm", 40) == 0.05                         # storm/M not stated → the any/M value
    assert damage_ratio(meth, "flood", 60) == 0.40 and event_probability(meth, "flood", 60) == 0.01
    assert meth.gap_text() is None
    assert valuation_haircut(meth, "seismic", 90) is None                       # neither seismic/VH nor any/VH
    assert "method.valuation_haircut (seismic/VH)" in meth.gap_text()
    assert valuation_haircut(meth, "flood", None) is None                       # unscored: nothing to read


def test_valuation_block_discounts_by_the_stated_haircut_an_override_wins_and_a_gap_stays_a_gap():
    meth = m()
    v = valuation_block(meth, "H", 1_000_000, None, outstanding_balance_eur=600_000, hazard="flood", score=60)
    assert v["recommended_discount_pct"] == 15.0 and v["discounted_value_eur"] == 850_000
    assert v["climate_adjusted_ltv_pct"] == pytest.approx(100 * 600_000 / 850_000, abs=0.01)
    o = valuation_block(meth, "H", 1_000_000, {"override_discount_pct": 20.0}, hazard="flood", score=60)
    assert o["effective_discount_pct"] == 20.0 and o["discounted_value_eur"] == 800_000
    g = valuation_block(meth, "VH", 1_000_000, None, hazard="seismic", score=90)
    assert g["discounted_value_eur"] is None and "seismic/VH" in g["gap"]


def test_at_risk_is_the_stated_level_and_unknown_without_it():
    assert at_risk(m(), 50) is True and at_risk(m(), 49.9) is False and at_risk(m(), None) is False
    assert at_risk(Method.of({}, PE), 80) is None


def test_pricing_is_the_chain_on_stated_inputs_and_premium_uses_the_stated_loadings():
    p = price_policy(m(), 60, 1_000_000, 0.02, hazard="flood")
    assert p["scenario_loss_eur"] == 400_000 and p["net_scenario_loss_eur"] == 380_000
    assert p["expected_annual_loss_eur"] == 3_800 and p["return_period_years"] == 100
    assert technical_premium(m(), 3_800, 1_000_000)["technical_premium_eur"] == pytest.approx(3_800 / 0.70)
    gap = price_policy(m(), 90, 1_000_000, hazard="flood")                  # flood/VH damage ratio not stated
    assert gap["expected_annual_loss_eur"] is None
    assert technical_premium(Method.of({}, PE), 3_800, 1_000_000)["technical_premium_eur"] is None


def test_a_policy_is_the_sum_of_its_perils_and_one_unstated_peril_makes_it_a_gap():
    assert insured_peril("flood") and not insured_peril("drought")
    hz = [{"hazard": "flood", "score": 60}, {"hazard": "storm", "score": 40}, {"hazard": "drought", "score": 95}]
    p = price_perils(m(), hz, 1_000_000)
    assert {c["hazard"] for c in p["perils"]} == {"flood", "storm"}
    assert p["expected_annual_loss_eur"] == pytest.approx(4_000 + 2_000)
    q = price_perils(m(), hz + [{"hazard": "seismic", "score": 80}], 1_000_000)
    assert q["expected_annual_loss_eur"] is None and q["technical_premium_eur"] is None and q["gap"]   # never a partial sum


def test_property_insurance_cost_needs_the_insured_value():
    hz = [{"hazard": "flood", "score": 60}]
    assert "sum_insured_eur" in noi_impact(m(), hz, None, 100_000)["gap"]
    r = noi_impact(m(), hz, 2_000_000, 100_000)
    assert r["technical_premium_eur"] == pytest.approx(8_000 / 0.70) and r["noi_impact_pct"] == pytest.approx(100 * 8_000 / 0.70 / 100_000, abs=0.01)


def test_bank_expected_loss_is_exposure_times_stated_probability_times_stated_damage():
    assert annual_expected_loss(m(), 1_000_000, 60, "flood")["annual_el_eur"] == 4_000
    assert annual_expected_loss(m(), 1_000_000, 90, "flood")["annual_el_eur"] is None
    nodes = {2025: 60.0, 2030: 60.0}
    assert lifetime_expected_loss(m(), 1_000_000, nodes, 3, "flood") == 12_000
    assert lifetime_expected_loss(m(), 1_000_000, nodes, None, "flood") is None       # no maturity: no default tenor


def test_value_loss_band_and_monte_carlo_var_are_gaps_until_stated():
    assets = [{"value_eur": 1_000_000, "headline_score": 60, "headline_hazard": "flood",
               "hazards": [{"hazard": "flood", "ci_lo": 45, "ci_hi": 80}], "valuation": {}}]
    b = value_loss_band(m(), assets)
    assert b["expected_value_loss_eur"] == 150_000 and b["loss_low_eur"] == 50_000 and b["loss_high_eur"] == 300_000
    assert value_loss_band(Method.of({}, PE), assets)["expected_value_loss_eur"] is None
    h = [{"position_value_eur": 1_000_000, "score": 60, "hazard": "flood"}]
    r = monte_carlo_var(m(), h, "o", "baseline", "current", VAR_SIMULATIONS)
    assert r["median_loss_eur"] <= r["var95_eur"] <= r["var99_eur"] <= 1_000_000 * 0.15 * 1.4 + 1
    assert monte_carlo_var(Method.of({("method.valuation_haircut", "flood/H"): 0.15}, PE), h, "o", "b", "c",
                           VAR_SIMULATIONS)["var95_eur"] is None


def test_combined_var_reads_the_stated_stranded_share_for_the_scenario_and_horizon():
    stated = {**FLOOD, ("method.transition_var_relative_uncertainty", None): 0.5,
              ("method.stranded_share", "C24@disorderly_2c/2030"): 0.2, ("method.stranded_share", "any@disorderly_2c/2030"): 0.0}
    h = [{"position_value_eur": 1_000_000, "headline_score": 60, "headline_hazard": "flood", "nace_code": "24.10",
          "hazards": [], "valuation": {}},
         {"position_value_eur": 1_000_000, "headline_score": 60, "headline_hazard": "flood", "nace_code": "62.01",
          "hazards": [], "valuation": {}}]
    r = combined_climate_var(Method.of(stated, PE), h, "o", "disorderly_2c", "2030", VAR_SIMULATIONS, "independent")
    assert r["transition_expected_eur"] == 200_000 and r["physical_expected_eur"] == 300_000
    assert r["combined_expected_eur"] == pytest.approx(1_000_000 * (1 - 0.85 * 0.8) + 1_000_000 * 0.15)
    other = combined_climate_var(Method.of(stated, PE), h, "o", "orderly_1_5c", "2050", VAR_SIMULATIONS, "independent")
    assert other["available"] is False and "C24@orderly_1_5c/2050" in other["gap"]     # never another scenario's share


def test_resilience_capex_on_stated_effectiveness_and_capex_share():
    stated = {**FLOOD, ("method.adaptation_effectiveness", "flood"): 0.5, ("method.resilience_capex_share", "H"): 0.025}
    props = [{"property_value_eur": 10_000_000, "headline_score": 60, "headline_hazard": "flood", "valuation": {}}]
    r = resilience_capex_plan(Method.of(stated, PE), props)
    top = r["top_properties"][0]
    assert top["physical_loss_eur"] == 1_500_000 and top["avoided_loss_eur"] == 750_000 and top["resilience_capex_eur"] == 250_000
    assert top["benefit_cost_ratio"] == 3.0 and "taxonomy_adaptation_aligned_capex_eur" not in r
    assert resilience_capex_plan(m(), props)["reason"] == "gap"


def test_the_catastrophe_simulation_refuses_a_book_with_an_unstated_peril():
    hz = [{"hazard": "flood", "score": 60}, {"hazard": "seismic", "score": 80}]
    pol = {"policy_id": "p1", "region": "A", "pricing": price_perils(m(), hz, 1_000_000)}
    r = catastrophe_accumulation([pol], "o", "baseline", "current", pml_return_period=250)
    assert r["available"] is False and r["reason"] == "gap"
