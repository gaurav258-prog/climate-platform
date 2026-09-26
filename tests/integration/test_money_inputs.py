"""Multi-currency phase 1b: every money input outside the intake pipeline declares its currency (never assumed) and
converts by the agreed policy — balances at the closing rate of the book date, flows at the period average — keeping
what was sent and the rate (money_source). Rows that can't be used are reported with the reason, never skipped
silently."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

import services.governance.gl_recon as G
import services.governance.seasonal_arrears as A
from core.db.session import get_session
from services.intake.money import MoneyError, convert_amount
from services.reference.fx import average_rate, rate_for
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
BOOK = date(2026, 6, 30)


def test_convert_amount_rules():
    with get_session() as s:
        assert convert_amount(s, "1,000", "EUR", BOOK)["eur"] == 1000.0
        usd = convert_amount(s, 1000, "usd", BOOK)
        assert usd["eur"] == pytest.approx(round(1000 * rate_for(s, "USD", BOOK)["rate"], 2)) and usd["rate"]["policy"] == "closing"
        flow = convert_amount(s, 1000, "USD", BOOK, flow=True)
        assert flow["eur"] == pytest.approx(round(1000 * average_rate(s, "USD", BOOK - timedelta(days=364), BOOK)["rate"], 2))
        for args, msg in (((1000, "", BOOK), "which currency"), ((1000, "USD", None), "which date"),
                          ((1000, "USD", date.today() + timedelta(days=9)), "future"), (("abc", "USD", BOOK), "not a number"),
                          ((1000, "ZZZ", BOOK), "no exchange rate")):
            with pytest.raises(MoneyError, match=msg):
                convert_amount(s, *args)


def _cleanup_gl(bid):
    with get_session() as s:
        s.execute(text("DELETE FROM gl_balance WHERE batch_id = CAST(:b AS uuid)"), {"b": bid})
        s.commit()


def test_gl_balances_declare_their_currency_and_date():
    rows = [{"account_code": "T-1", "account_name": "test USD", "balance": "1,000,000"},
            {"account_code": "T-2", "account_name": "test GBP row", "balance": "500000", "currency": "GBP"},
            {"account_code": "T-3", "account_name": "no date", "balance": "10", "currency": "CHF", "as_of_date": ""},
            {"account_code": "", "balance": "1"}]
    with get_session() as s:
        res = G.ingest(s, BANK_ORG, rows, None, currency="USD", book_date="2026-06-30")
    try:
        assert res["rows"] == 3 and res["n_skipped"] == 1 and "account_code" in res["skipped"][0]["reason"]
        with get_session() as s:
            got = {r[0]: (float(r[1]), r[2]) for r in s.execute(text(
                "SELECT account_code, balance_eur, money_source FROM gl_balance WHERE batch_id = CAST(:b AS uuid)"), {"b": res["batch_id"]})}
            assert got["T-1"][0] == pytest.approx(round(1e6 * rate_for(s, "USD", BOOK)["rate"], 2))
            assert got["T-2"][1]["currency"] == "GBP" and got["T-2"][1]["native"] == {"balance": 500000.0}
        with get_session() as s:
            none = G.ingest(s, BANK_ORG, [{"account_code": "T-9", "balance": "5"}], None)          # nothing declared
        assert none["rows"] == 0 and "currency" in none["skipped"][0]["reason"]
    finally:
        _cleanup_gl(res["batch_id"])


def test_arrears_exposure_needs_its_currency_but_the_row_stays_without_one():
    rows = [{"loan_ref": "T-A1", "days_past_due": "40", "exposure": "9800000", "currency": "BRL", "as_of_date": "2026-06-30"},
            {"loan_ref": "T-A2", "days_past_due": "10"},                                          # no exposure: fine
            {"loan_ref": "T-A3", "days_past_due": "10", "exposure": "5", "as_of_date": "2026-06-30"}]   # no currency
    with get_session() as s:
        res = A.ingest(s, BANK_ORG, rows, None)
    try:
        assert res["rows"] == 2 and res["skipped"][0]["row"] == 4 and "currency" in res["skipped"][0]["reason"]
        with get_session() as s:
            exp = s.execute(text("SELECT CAST(exposure_eur AS FLOAT) FROM loan_arrears WHERE batch_id = CAST(:b AS uuid) "
                                 "AND loan_ref = 'T-A1'"), {"b": res["batch_id"]}).scalar()
            assert exp == pytest.approx(round(9.8e6 * rate_for(s, "BRL", BOOK)["rate"], 2))
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM loan_arrears WHERE batch_id = CAST(:b AS uuid)"), {"b": res["batch_id"]})
            s.commit()


def test_site_value_is_a_balance_and_throughput_a_flow():
    from services.intelligence.company_sites import site_amounts
    with get_session() as s:
        v, tp, ms = site_amounts(s, "2000000", "5000000", "USD", "2026-06-30")
        assert v == pytest.approx(round(2e6 * rate_for(s, "USD", BOOK)["rate"], 2))
        assert tp == pytest.approx(round(5e6 * average_rate(s, "USD", BOOK - timedelta(days=364), BOOK)["rate"], 2))
        assert [r["policy"] for r in ms["rates"]] == ["closing", "average"]
        with pytest.raises(MoneyError):
            site_amounts(s, "2000000", None, None, "2026-06-30")
        assert site_amounts(s, None, None, None, None) == (None, None, None)       # no amounts: nothing to declare


def test_fund_issuer_financials_in_their_own_currency():
    from api.routers.funds import Holding, _issuer_financials_eur
    with pytest.raises(ValueError, match="financials_currency"):
        Holding(isin="US0000000001", market_value_eur=1e6, revenue=5e9)
    h = Holding(isin="US0000000001", market_value_eur=1e6, revenue=5e9, evic=2e10, financials_currency="USD", reporting_year=2025)
    with get_session() as s:
        f = _issuer_financials_eur(s, h)
        d = date(2025, 12, 31)
        assert f["revenue_eur"] == pytest.approx(round(5e9 * average_rate(s, "USD", d - timedelta(days=364), d)["rate"], 2))
        assert f["evic_eur"] == pytest.approx(round(2e10 * rate_for(s, "USD", d)["rate"], 2))
        assert f["money_source"]["native"] == {"revenue": 5e9, "evic": 2e10}
    eur = Holding(isin="US0000000001", market_value_eur=1e6, revenue_eur=7e8)
    with get_session() as s:
        assert _issuer_financials_eur(s, eur)["revenue_eur"] == 7e8


def test_per_loan_attributes_match_by_id_refuse_ambiguous_names_and_convert_evic(intake_client):
    from services.ingest.portfolio_ingest import ingest_bank_assets
    tag = uuid.uuid4().hex[:8]
    name = f"TEST-ATTR-{tag}"
    base = {"asset_name": name, "asset_type": "cre", "latitude": 48.85, "longitude": 2.35, "appraised_value_eur": 1e6,
            "sector": "RE", "counterparty_evic_eur": 1e8}
    with get_session() as s:
        ingest_bank_assets(s, BANK_ORG, [{**base, "external_ref": f"{tag}-A"}, {**base, "latitude": 48.9, "external_ref": f"{tag}-B"}],
                           dispatch_scoring=False)
        s.commit()
    csv = (f"external_ref,asset_name,counterparty_evic_eur,currency,book_date\n"
           f"{tag}-A,,300000000,USD,2026-06-30\n"
           f",{name},400000000,USD,2026-06-30\n").encode()
    try:
        r = intake_client.post("/v1/bank/assets/attributes/upload", headers=intake_client.maker, files={"file": ("attrs.csv", csv)})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["n_matched"] == 1 and b["n_ambiguous"] == 1 and b["ambiguous"] == [name]
        with get_session() as s:
            evic = s.execute(text("SELECT CAST(x.counterparty_evic_eur AS FLOAT) FROM ext_banking x JOIN portfolio_entities e "
                                  "ON e.entity_id = x.entity_id WHERE e.external_ref = :r"), {"r": f"{tag}-A"}).scalar()
            assert evic == pytest.approx(round(3e8 * rate_for(s, "USD", BOOK)["rate"], 2))
    finally:
        with get_session() as s:
            ids = [r[0] for r in s.execute(text("SELECT entity_id FROM portfolio_entities WHERE entity_name = :n"), {"n": name})]
            s.execute(text("DELETE FROM ext_banking WHERE entity_id = ANY(:i)"), {"i": ids})
            s.execute(text("DELETE FROM portfolio_entities WHERE entity_id = ANY(:i)"), {"i": ids})
            s.commit()
