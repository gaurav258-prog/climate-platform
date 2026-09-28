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


def test_a_shared_symbol_is_never_added_until_the_filing_says_which_currency(session_rolled_back):
    s = session_rolled_back
    got = _combine(s, [_f(5, "$"), _f(7, "$")], "EUR")
    assert got["value"] is None and "state the filing's currency" in got["note"]


def test_an_upload_declares_its_currency_and_period_end(session_rolled_back):
    import io

    from openpyxl import Workbook

    import services.governance.prior_filings as PF
    from sqlalchemy import text
    s = session_rolled_back
    wb = Workbook()
    ws = wb.active
    ws.append(["Total book value", "$1,500,000"])
    ws.append(["Scope 3 financed emissions (tCO2e)", 1640000])
    buf = io.BytesIO()
    wb.save(buf)
    org = "11111111-1111-4111-8111-111111111111"
    f = PF.create_from_upload(s, org, None, framework="bank_p3esg", period_label="FY2024", entity_name=None,
                              filename="p3.xlsx", data=buf.getvalue(), currency="cad", period_end="2024-09-30")
    try:
        _check_upload(s, f, PF, buf)
    finally:                                     # create_from_upload commits: remove what it wrote
        PF.delete_filing(s, f["filing_id"], org)


def _check_upload(s, f, PF, buf):
    from sqlalchemy import text
    org = "11111111-1111-4111-8111-111111111111"
    units = {r[0]: r[1] for r in s.execute(text("SELECT label, unit FROM reported_figure WHERE filing_id = CAST(:f AS uuid)"),
                                           {"f": f["filing_id"]})}
    assert units["Total book value"] == "CAD" and units["Scope 3 financed emissions (tCO2e)"] == "tCO2e"
    pe = s.execute(text("SELECT period_end, currency FROM reported_filing WHERE filing_id = CAST(:f AS uuid)"), {"f": f["filing_id"]}).first()
    assert (pe[0].isoformat(), pe[1]) == ("2024-09-30", "CAD")
    with pytest.raises(PF.FilingError, match="ISO 4217"):
        PF.create_from_upload(s, org, None, framework="bank_p3esg", period_label="FY2024", entity_name=None,
                              filename="p3.xlsx", data=buf.getvalue(), currency="XYZ")
