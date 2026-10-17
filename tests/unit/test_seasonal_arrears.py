"""Seasonal-arrears classifier — three tiers, no DB: seasonal (calendar) > climate-attributed (observed
national yield shock) > genuine (the true residual)."""
from core import messages
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
    assert r["code"] == "agri.data.arrears.bad_harvest" and r["params"]["fall"] == "5.0" and r["params"]["country"] == "BR"


def test_out_of_window_no_shock_is_genuine():
    r = classify_loan("soy", dpd=60, month=6, country="BR", yield_shocks={}, season_year=2024)
    assert r["classification"] == "genuine"


def test_no_country_is_never_checked_for_a_shock_and_says_so():
    # a shock keyed the SAME crop/year but a DIFFERENT country must not leak in, and the reason must be honest
    shocks = {("soy", "BR", 2024): -5.04}
    r = classify_loan("soy", dpd=60, month=6, country=None, yield_shocks=shocks, season_year=2024)
    assert r["classification"] == "genuine"
    assert r["code"] == "agri.data.arrears.outside_window" and r["country_checked"] is False


def test_beyond_the_seasonal_cap_falls_through_to_the_shock_check():
    shocks = {("cocoa", "CI", 2024): -9.0}
    r = classify_loan("cocoa", dpd=200, month=11, country="CI", yield_shocks=shocks, season_year=2024)
    assert r["classification"] == "climate_attributed"   # in-window but dpd > cap -> not seasonal, but shock explains it


def test_unknown_crop_gets_no_seasonal_allowance():
    r = classify_loan("quinoa", dpd=30, month=11, country="PE", yield_shocks={}, season_year=2026)
    assert r["classification"] == "genuine"
    assert r["code"] == "agri.data.arrears.no_calendar"


def test_threshold_is_the_documented_minus_five_percent():
    assert YIELD_SHOCK_THRESHOLD_PCT == -5.0


def test_every_reason_is_a_catalogue_message_in_customer_words():
    # each call's reason renders with its own values: no placeholder left unfilled, no code on the screen
    cases = [classify_loan("wheat", 45, 11, "ES", {}, 2026),                                   # seasonal
             classify_loan("soy", 60, 6, "BR", {("soy", "BR", 2024): -5.04}, 2024),           # bad harvest
             classify_loan("cocoa", 200, 11, None, {}, 2024),                                 # over the limit
             classify_loan("soy", 60, 6, "BR", {}, 2024),                                     # outside the window
             classify_loan("quinoa", 30, 11, "PE", {}, 2026),                                 # no calendar
             classify_loan(None, 30, 11, "PE", {}, 2026)]                                     # no crop
    assert {c["code"] for c in cases} == {"agri.data.arrears.seasonal", "agri.data.arrears.bad_harvest",
                                          "agri.data.arrears.over_limit", "agri.data.arrears.outside_window",
                                          "agri.data.arrears.no_calendar", "agri.data.arrears.no_crop"}
    for c in cases:
        m = messages.render(c["code"], **c["params"])
        assert "{" not in m["label"] and all("{" not in v for v in m["detail"].values())
        assert not messages.INTERNAL.search(m["label"])
    assert messages.render(cases[0]["code"], **cases[0]["params"])["detail"]["what"].startswith("45 days past due in November")
