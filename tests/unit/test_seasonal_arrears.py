"""Seasonal-arrears classifier — three tiers, no DB: seasonal (calendar) > climate-attributed (observed
national yield shock) > genuine (the true residual)."""
from services.governance.seasonal_arrears import (
    YIELD_SHOCK_THRESHOLD_PCT,
    classify_loan,
)


def test_in_window_and_under_cap_is_seasonal():
    r = classify_loan("wheat", dpd=45, month=11, country="ES", yield_shocks={}, season_year=2026)
    assert r["classification"] == "seasonal"


def test_seasonal_wins_even_when_a_shock_also_exists():
    # the calendar explanation is checked first -- a loan already explained by carry-over isn't double-counted
    shocks = {("wheat", "ES", 2026): -12.0}
    r = classify_loan("wheat", dpd=45, month=11, country="ES", yield_shocks=shocks, season_year=2026)
    assert r["classification"] == "seasonal"


def test_out_of_window_with_observed_shock_is_climate_attributed():
    shocks = {("soy", "BR", 2024): -5.04}
    r = classify_loan("soy", dpd=60, month=6, country="BR", yield_shocks=shocks, season_year=2024)
    assert r["classification"] == "climate_attributed"
    assert "5.0%" in r["rationale"] or "5.04" in r["rationale"] or "-5.0" in r["rationale"]


def test_out_of_window_no_shock_is_genuine():
    r = classify_loan("soy", dpd=60, month=6, country="BR", yield_shocks={}, season_year=2024)
    assert r["classification"] == "genuine"


def test_no_country_is_never_checked_for_a_shock_and_says_so():
    # a shock keyed the SAME crop/year but a DIFFERENT country must not leak in, and the reason must be honest
    shocks = {("soy", "BR", 2024): -5.04}
    r = classify_loan("soy", dpd=60, month=6, country=None, yield_shocks=shocks, season_year=2024)
    assert r["classification"] == "genuine"
    assert "no country on record" in r["rationale"]


def test_beyond_the_seasonal_cap_falls_through_to_the_shock_check():
    shocks = {("cocoa", "CI", 2024): -9.0}
    r = classify_loan("cocoa", dpd=200, month=11, country="CI", yield_shocks=shocks, season_year=2024)
    assert r["classification"] == "climate_attributed"   # in-window but dpd > cap -> not seasonal, but shock explains it


def test_unknown_crop_gets_no_seasonal_allowance():
    r = classify_loan("quinoa", dpd=30, month=11, country="PE", yield_shocks={}, season_year=2026)
    assert r["classification"] == "genuine"
    assert "no seasonal calendar" in r["rationale"]


def test_threshold_is_the_documented_minus_five_percent():
    assert YIELD_SHOCK_THRESHOLD_PCT == -5.0
