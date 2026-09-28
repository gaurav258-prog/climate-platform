"""Multi-currency phase 5: the screens show engine (EUR) amounts in the organisation's presentation currency — balances
at the closing rate, yearly flows at the 12-month average (or closing, where the governed fx_flow_rate says so) — and
never relabel: a currency without a rate falls back to EUR and says so. An edit of a location's amounts states its
currency and book date and is converted like an add; an invoice carries the price book's currency.
Runs inside a rolled-back transaction."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from services.governance import display_currency as DC
from services.governance.billing import PRICE_CURRENCY, get_billing
from services.governance.location_governance import LocationMoneyError, apply_location_change, convert_money_changes
from services.governance.reporting_settings import upsert_reporting_settings
from services.reference.fx import average_rate, rate_for
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def test_eur_presentation_translates_nothing(session_rolled_back):
    s = session_rolled_back
    upsert_reporting_settings(s, BANK_ORG, {"presentation_currency": "EUR"}, None)
    v = DC.view(s, BANK_ORG)
    assert v["currency"] == "EUR" and v["balance"]["units_per_eur"] == 1.0 and v["flow"]["units_per_eur"] == 1.0
    assert DC.balance(2_500_000, v) == "€2.5m" and DC.flow(-4_100_000, v) == "−€4.1m"


def test_usd_presentation_uses_closing_for_balances_and_the_average_for_flows(session_rolled_back):
    s = session_rolled_back
    upsert_reporting_settings(s, BANK_ORG, {"presentation_currency": "USD"}, None)
    today = date.today()
    v = DC.view(s, BANK_ORG, today)
    closing = rate_for(s, "USD", today)
    avg = average_rate(s, "USD", today - timedelta(days=364), today)
    u_close = closing["units_per_eur"] or 1 / closing["rate"]
    assert v["currency"] == "USD" and v["balance"]["units_per_eur"] == pytest.approx(u_close, rel=1e-6)
    assert v["flow"]["units_per_eur"] == pytest.approx(avg["units_per_eur"] or 1 / avg["rate"], rel=1e-6)
    assert DC.balance(1_000_000, v) == f"US${1_000_000 * u_close / 1e6:.1f}m"
    with DC.using(s, BANK_ORG, v):                       # server text written inside a request uses the same view
        assert DC.balance(1_000_000) == DC.balance(1_000_000, v)
    assert DC.balance(1_000_000) == "€1.0m"               # outside one: EUR, untranslated — never relabelled


def test_a_currency_without_any_rate_falls_back_to_eur_and_says_so(session_rolled_back):
    s = session_rolled_back
    upsert_reporting_settings(s, BANK_ORG, {"presentation_currency": "USD"}, None)
    s.execute(text("UPDATE org_reporting_settings SET presentation_currency = 'XTS' WHERE org_id = :o"), {"o": BANK_ORG})
    v = DC.view(s, BANK_ORG)
    assert v["currency"] == "EUR" and "XTS" in v["note"] and v["balance"]["units_per_eur"] == 1.0


def _site(s):
    r = s.execute(text("""SELECT site_id::text AS id, org_id::text AS org FROM sc_company_sites
                          WHERE annual_value_eur IS NOT NULL LIMIT 1""")).mappings().first()
    if not r:
        pytest.skip("no seeded site")
    return r


def test_a_location_edit_in_usd_converts_on_the_book_date_and_records_what_was_sent(session_rolled_back):
    s = session_rolled_back
    site = _site(s)
    bd = date.today() - timedelta(days=30)
    changes, ms = convert_money_changes(s, site["org"], "site", {"annual_value_eur": 2_000_000.0, "name": "Renamed"}, "USD", bd.isoformat())
    u = rate_for(s, "USD", bd)
    assert changes["name"] == "Renamed"
    assert changes["annual_value_eur"] == pytest.approx(2_000_000.0 * u["rate"], abs=0.01)     # a balance: closing rate
    f = ms["fields"]["annual_value_eur"]
    assert (f["amount"], f["currency"], f["book_date"], f["policy"], f["origin"]) == (2_000_000.0, "USD", bd.isoformat(), "closing", "manual_edit")
    apply_location_change(s, "supply.site.update", {"target_id": site["id"], "changes": changes, "money_source": ms},
                          actor_user_id=None, org_id=site["org"])
    row = s.execute(text("SELECT CAST(annual_value_eur AS FLOAT) v, money_source FROM sc_company_sites WHERE site_id = CAST(:i AS uuid)"),
                    {"i": site["id"]}).mappings().first()
    assert row["v"] == pytest.approx(changes["annual_value_eur"], abs=0.01)
    assert row["money_source"]["fields"]["annual_value_eur"]["currency"] == "USD"


def test_a_location_edit_amount_without_a_currency_is_refused(session_rolled_back):
    s = session_rolled_back
    site = _site(s)
    with pytest.raises(LocationMoneyError):
        convert_money_changes(s, site["org"], "site", {"annual_throughput_eur": 5.0}, None, date.today().isoformat())
    same, ms = convert_money_changes(s, site["org"], "site", {"name": "only a rename"}, None, None)
    assert same == {"name": "only a rename"} and ms is None                 # no amount, nothing to declare


def test_invoices_and_prices_carry_the_price_book_currency(session_rolled_back):
    b = get_billing(session_rolled_back, BANK_ORG)
    assert b["price_currency"] == PRICE_CURRENCY
    assert all(i["currency"] for i in b["invoices"])
