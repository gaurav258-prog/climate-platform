"""Loan-book transition overlay — financed emissions (reported or NACE-estimated) + a carbon-price
transition expected-loss from the modelled stranded fraction. Pure — no DB."""
from services.scoring.loan_transition import loan_transition_overlay


def _loan(nace, outstanding, revenue=100_000_000, ghg1=None, ghg2=None):
    return {"asset_id": nace + "-x", "asset_name": "Co " + nace, "nace_code": nace,
            "revenue_eur": revenue, "ghg1": ghg1, "ghg2": ghg2, "ghg3": None,
            "outstanding_loan_balance_eur": outstanding, "value_eur": outstanding}


def test_reported_emissions_flow_and_transition_el():
    # power generation (NACE 35), reported emissions → transition score + EL present.
    book = [_loan("35.11", 100_000_000, ghg1=400_000, ghg2=50_000)]
    r = loan_transition_overlay(book, "disorderly_2c", "2050")
    assert r["available"]
    assert r["n_scored"] == 1 and r["n_emissions_estimated"] == 0
    assert r["emissions_reported_pct"] == 100.0
    assert r["financed_emissions_tco2e"] == 450_000
    assert r["transition_expected_loss_eur"] > 0
    # transition EL is bounded by the outstanding (a fraction of it)
    assert r["transition_expected_loss_eur"] <= 100_000_000
    assert r["top_exposures"][0]["emissions_source"] == "reported"


def test_missing_emissions_are_estimated_and_flagged():
    # no reported ghg, but NACE + revenue → estimate_emissions fills scope 1+2, flagged 'estimated'.
    book = [_loan("35.11", 100_000_000, revenue=200_000_000, ghg1=None, ghg2=None)]
    r = loan_transition_overlay(book, "disorderly_2c", "2050")
    assert r["available"]
    assert r["n_emissions_estimated"] == 1
    assert r["emissions_reported_pct"] == 0.0
    assert r["financed_emissions_tco2e"] > 0          # filled from the sector intensity
    assert r["top_exposures"][0]["emissions_source"] == "estimated"


def test_high_carbon_sector_has_more_transition_risk_than_low():
    coal = loan_transition_overlay([_loan("05.10", 100_000_000, ghg1=500_000)], "orderly_1_5c", "2050")
    services = loan_transition_overlay([_loan("62.01", 100_000_000, ghg1=500)], "orderly_1_5c", "2050")
    assert coal["transition_expected_loss_eur"] > services["transition_expected_loss_eur"]
    assert coal["exposure_weighted_transition_score"] >= services["exposure_weighted_transition_score"]


def test_by_sector_concentration_and_ordering():
    book = [_loan("35.11", 200_000_000, ghg1=400_000), _loan("62.01", 50_000_000, ghg1=200)]
    r = loan_transition_overlay(book, "disorderly_2c", "2050")
    # sectors sorted by transition EL desc → the power sector (35) leads
    assert r["by_sector"][0]["nace_section"] == "35"


def test_no_signal_is_unavailable():
    assert loan_transition_overlay([], "disorderly_2c", "2050")["available"] is False
    # a sector with no transition thesis and no emissions → no honest signal
    noise = [{"nace_code": "88.10", "revenue_eur": None, "ghg1": None, "ghg2": None, "ghg3": None,
              "outstanding_loan_balance_eur": 1_000_000, "value_eur": 1_000_000}]
    assert loan_transition_overlay(noise, "disorderly_2c", "2050")["available"] is False
