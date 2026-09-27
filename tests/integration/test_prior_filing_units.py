"""Prior filings (multi-currency phase 4): a datapoint's figures are only added when they share a unit; money in
different currencies is converted to the organisation's presentation currency at the period-end closing rate; a
unit that changes between years stops the trend being projected."""
from datetime import date

import pytest

from services.governance.prior_filings import _combine
from services.reference.fx import rate_for

pytestmark = pytest.mark.integration


def _f(v, u, period="2024"):
    return {"value_num": v, "unit": u, "period_label": period, "period_end": None}


def test_money_in_two_currencies_is_converted_before_it_is_added(session_rolled_back):
    s = session_rolled_back
    got = _combine(s, [_f(1_000_000, "EUR"), _f(1_000_000, "USD")], "EUR")
    usd = rate_for(s, "USD", date(2024, 12, 31))["units_per_eur"]
    assert got["unit"] == "EUR" and got["value"] == pytest.approx(1_000_000 + 1_000_000 / usd)
    assert got["converted_from"] == {"EUR": 1_000_000, "USD": 1_000_000} and got["rate_date"] == "2024-12-31"


def test_different_units_are_never_added(session_rolled_back):
    s = session_rolled_back
    for figs in ([_f(5, "tCO2e"), _f(7, "MWh")], [_f(5, "EUR"), _f(7, None)]):
        got = _combine(s, figs, "EUR")
        assert got["value"] is None and len(got["mixed_units"]) == 2
    assert _combine(s, [_f(5, "tCO2e"), _f(7, "tCO2e")], "EUR") == {"value": 12.0, "unit": "tCO2e"}
    no_year = _combine(s, [_f(1, "USD", period="FY")], "EUR")
    assert no_year["value"] is None and "no period end" in no_year["note"]


def test_a_fund_shows_its_value_in_its_own_base_currency(session_rolled_back):
    from services.fund_disclosure import fund_base_view
    s, d = session_rolled_back, date(2025, 12, 31)
    usd = rate_for(s, "USD", d)["units_per_eur"]
    v = fund_base_view(s, "USD", d, {"total_value": 1_000_000.0})
    assert v["currency"] == "USD" and v["total_value"] == round(1_000_000 * usd) and v["rate"]["units_per_eur"] == usd
    assert fund_base_view(s, None, d, {"total_value": 5.4}) == {"currency": "EUR", "as_of": "2025-12-31", "total_value": 5}
