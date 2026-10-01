"""Loan-book transition overlay on the institution's stated method (E69) — financed emissions (reported or the flagged
EXIOBASE sector estimate), the carbon cost at the STATED carbon price, and the transition expected loss = outstanding ×
the STATED stranded share of the counterparty's NACE division. Nothing is supplied by the platform: an unstated
parameter, or a loan without an outstanding balance, is a named gap — never a number. Pure — no DB."""
from datetime import date

import pytest

from ml.scoring.transition_risk import transition_block
from services.money.params import Method
from services.scoring.loan_transition import loan_transition_overlay

PE = date(2025, 12, 31)
S, H = "disorderly_2c", "2050"
# test values for the mechanics only — nobody's method
STATED = {("method.carbon_price", f"{S}/{H}"): 200.0,
          ("method.stranded_share", f"D35@{S}/{H}"): 0.20,
          ("method.stranded_share", f"any@{S}/{H}"): 0.02}


def _m(values=STATED):
    return Method.of(values, PE)


def _loan(nace, outstanding, revenue=100_000_000, ghg1=None, ghg2=None):
    return {"asset_id": nace + "-x", "asset_name": "Co " + nace, "nace_code": nace, "revenue_eur": revenue,
            "ghg1": ghg1, "ghg2": ghg2, "ghg3": None, "outstanding_loan_balance_eur": outstanding, "value_eur": 5 * (outstanding or 1)}


def test_the_expected_loss_is_the_outstanding_times_the_stated_stranded_share_of_its_division():
    r = loan_transition_overlay(_m(), [_loan("35.11", 100_000_000, ghg1=400_000, ghg2=50_000),
                                       _loan("62.01", 50_000_000, ghg1=500)], S, H)
    assert r["available"] and "gap" not in r
    assert r["transition_expected_loss_eur"] == 100_000_000 * 0.20 + 50_000_000 * 0.02     # own division, then 'any'
    assert r["financed_emissions_tco2e"] == 450_500 and r["emissions_reported_pct"] == 100.0
    assert r["by_sector"][0]["nace_division"] == "D35" and r["by_sector"][0]["label"].startswith("Electricity")


def test_the_carbon_cost_is_the_emissions_at_the_stated_price_and_the_score_the_larger_share():
    blk = transition_block(_m(), 400_000, 0, 100_000_000, "D35", S, H)
    assert blk["carbon_price_eur_per_tonne"] == 200.0
    assert blk["carbon_price_impact"] == pytest.approx(400_000 * 200.0)
    assert blk["carbon_cost_pct_of_revenue"] == pytest.approx(80.0)                   # 80m of 100m revenue
    assert blk["transition_risk_score"] == 80.0 and blk["dominant_channel"] == "carbon_cost"
    assert blk["carbon_intensity_tco2e_per_meur"] == 4000.0


def test_missing_emissions_are_estimated_and_flagged():
    r = loan_transition_overlay(_m(), [_loan("35.11", 100_000_000, revenue=200_000_000)], S, H)
    assert r["n_emissions_estimated"] == 1 and r["emissions_reported_pct"] == 0.0
    assert r["financed_emissions_tco2e"] > 0 and r["top_exposures"][0]["emissions_source"] == "estimated"


def test_an_unstated_parameter_is_a_named_gap_not_a_number():
    r = loan_transition_overlay(_m({}), [_loan("35.11", 100_000_000, ghg1=1000)], S, H)
    assert "transition_expected_loss_eur" not in r
    assert "method.stranded_share (D35@disorderly_2c/2050)" in r["gap"] and "method.carbon_price" in r["gap"]
    # a stranded share alone: the expected loss is computed, but without the carbon price the score is not
    only = {k: v for k, v in STATED.items() if k[0] == "method.stranded_share"}
    blk = transition_block(_m(only), 1000, 0, 100_000_000, "D35", S, H)
    assert blk["stranded_asset_pct"] == 20.0 and blk["transition_risk_score"] is None and "method.carbon_price" in blk["gap"]


def test_the_collateral_value_is_never_the_exposure():
    r = loan_transition_overlay(_m(), [_loan("35.11", None, ghg1=1000), _loan("62.01", 10_000_000, ghg1=10)], S, H)
    assert "transition_expected_loss_eur" not in r and "1 loan(s) have no outstanding balance" in r["gap"]


def test_revenue_in_another_currency_is_brought_back_to_eur():
    eur = loan_transition_overlay(_m(), [_loan("24.10", 100_000_000)], S, H)
    usd = loan_transition_overlay(_m(), [_loan("24.10", 117_500_000, revenue=117_500_000)], S, H, eur_per_unit=1 / 1.175)
    assert usd["financed_emissions_tco2e"] == eur["financed_emissions_tco2e"]
    a = transition_block(_m(), 1000, 0, 100_000_000, "D35", S, H)
    b = transition_block(_m(), 1000, 0, 117_500_000, "D35", S, H, eur_per_unit=1 / 1.175)
    assert b["carbon_cost_pct_of_revenue"] == pytest.approx(a["carbon_cost_pct_of_revenue"])
    assert b["carbon_price_impact"] == pytest.approx(a["carbon_price_impact"] * 1.175)   # in the book's currency


def test_an_empty_book_is_unavailable():
    assert loan_transition_overlay(_m(), [], S, H)["available"] is False
