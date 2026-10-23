"""An asset manager's funds and holdings by ISIN through its standard file (the product owner's decision of 2026-10-23):
the Funds sheet states each fund through the one fund registry, the Fund holdings sheet lands each position through the
one onboarding — the same as POST /v1/funds and POST /v1/funds/{id}/holdings — with the intake's checks, its conversion
of a value in another currency at the row's as-of date, and the amount as sent kept on the position. Service level inside
a rolled-back transaction; the securities are cached first so no register is called."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from services.ingest.fund_books import isin_ok
from services.intake import workbooks
from tests.integration.test_intake_every_sector import _org_and_admin
from tests.integration.test_intake_workbook import _filled

pytestmark = pytest.mark.integration
EUR_ISIN, USD_ISIN = "US00TESTWB15", "US00TESTWB23"          # well-formed (check digit right), cached below


def _cache_securities(s) -> None:
    iid = s.execute(text("""INSERT INTO issuers (name, issuer_type, country, source)
                            VALUES ('TEST-WB Issuer', 'corporate', 'US', 'manual') RETURNING issuer_id""")).scalar()
    for isin in (EUR_ISIN, USD_ISIN):
        s.execute(text("""INSERT INTO securities (isin, name, issuer_id, asset_class, source)
                          VALUES (:i, 'TEST-WB security', :iss, 'equity', 'manual')"""), {"i": isin, "iss": iid})
    s.execute(text("""INSERT INTO issuer_facilities (issuer_id, name, latitude, longitude, country, source)
                      VALUES (:i, 'HQ', 40.0, -74.0, 'US', 'manual')"""), {"i": iid})


def _send(s, org_id, user_id, books, tag, reason=None):
    return {r["book"]: r for r in workbooks.submit(s, org_id, "asset_manager", _filled("asset_manager", books), f"{tag}.xlsx",
                                                   user_id=user_id, currency="EUR", reason=reason)["sheets"]}


def test_funds_then_holdings_land_through_the_one_registry_and_onboarding(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "asset_manager")
    _cache_securities(s)
    fund = f"TEST-WB Fund {tag}"
    out = _send(s, org_id, user_id, {
        "funds": [{"fund_name": fund, "fund_type": "fund", "sfdr_classification": "Article 8", "base_currency": "EUR"}],
        "fund_holdings": [
            {"fund_name": fund, "isin": EUR_ISIN, "market_value_eur": 4_000_000, "book_date": "2024-03-01"},
            {"fund_name": fund, "isin": USD_ISIN, "market_value_eur": 1_000_000, "currency": "USD", "book_date": "2024-03-01"},
        ]}, tag)
    assert out["funds"]["state"] == "imported", out["funds"]
    assert out["fund_holdings"]["state"] == "imported", out["fund_holdings"]
    f = s.execute(text("SELECT fund_id::text, sfdr_classification FROM funds WHERE org_id = CAST(:o AS uuid) AND name = :n"),
                  {"o": org_id, "n": fund}).one()
    assert f[1] == "article_8"                                       # the customer's spelling matched to ours
    rows = {r["isin"]: r for r in s.execute(text("""
        SELECT s.isin, CAST(p.market_value_eur AS FLOAT) AS eur, CAST(p.market_value_native AS FLOAT) AS native, p.currency,
               p.as_of_date::text AS as_of, p.money_source
        FROM fund_positions p JOIN securities s ON s.security_id = p.security_id WHERE p.fund_id = CAST(:f AS uuid)"""),
        {"f": f[0]}).mappings()}
    assert set(rows) == {EUR_ISIN, USD_ISIN} and rows[EUR_ISIN]["as_of"] == "2024-03-01"
    usd = rows[USD_ISIN]
    assert usd["currency"] == "USD" and usd["native"] == 1_000_000.0 and 0 < usd["eur"] != 1_000_000.0   # converted, kept
    sent = usd["money_source"]["fields"]["market_value_eur"]
    assert sent["amount"] == 1_000_000.0 and sent["currency"] == "USD" and sent["origin"].startswith("batch:")
    audit = s.execute(text("""SELECT count(*) FROM access_audit_log WHERE org_id = CAST(:o AS uuid) AND action = 'fund.created'
                              AND target_id = :f AND actor_user_id = CAST(:u AS uuid)"""),
                       {"o": org_id, "f": f[0], "u": user_id}).scalar()
    assert audit == 1


def test_a_fund_restated_and_rows_that_cannot_stand_say_why(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "asset_manager")
    _cache_securities(s)
    fund = f"TEST-WB Fund {tag}"
    _send(s, org_id, user_id, {"funds": [{"fund_name": fund, "fund_type": "fund", "sfdr_classification": "article_8",
                                          "base_currency": "EUR"}]}, tag)
    out = _send(s, org_id, user_id, {
        "funds": [{"fund_name": fund, "fund_type": "fund", "sfdr_classification": "article_9", "base_currency": "EUR"}],
        "fund_holdings": [
            {"fund_name": "No such fund", "isin": EUR_ISIN, "market_value_eur": 1_000, "book_date": "2024-03-01"},
            {"fund_name": fund, "isin": "US00TESTWB16", "market_value_eur": 1_000, "book_date": "2024-03-01"},
            {"fund_name": fund, "isin": EUR_ISIN, "market_value_eur": 2_000, "book_date": "2024-03-01"},
        ]}, tag + "b", reason="Two lines are known to be wrong; checked by the fund desk")
    assert out["funds"]["state"] == "imported"
    assert s.execute(text("SELECT sfdr_classification FROM funds WHERE org_id = CAST(:o AS uuid) AND name = :n"),
                     {"o": org_id, "n": fund}).scalar() == "article_9"
    h = out["fund_holdings"]
    assert h["state"] == "awaiting_approval" and h["n_error"] == 2 and h["n_valid"] == 1, h
    from services.intake.pipeline import _load_batch
    errs = s.execute(text("SELECT gate_reasons FROM ingest_batches WHERE batch_id = CAST(:b AS uuid)"),
                     {"b": h["batch_id"]}).scalar()
    assert errs and _load_batch(s, org_id, h["batch_id"])["sheet"] == "Fund holdings"
    checked = workbooks.check(s, org_id, "asset_manager", _filled("asset_manager", {"fund_holdings": [
        {"fund_name": "No such fund", "isin": EUR_ISIN, "market_value_eur": 1_000, "book_date": "2024-03-01"},
        {"fund_name": fund, "isin": "US00TESTWB16", "market_value_eur": 1_000, "book_date": "2024-03-01"}]}), "x.xlsx",
        currency="EUR")
    said = " ".join(p for e in next(r for r in checked["sheets"] if r["book"] == "fund_holdings")["errors"] for p in e["problems"])
    assert "not one of your funds" in said and "not a valid ISIN" in said


def test_isin_check_digit():
    assert isin_ok("DE0007164600") and isin_ok("US0378331005") and isin_ok(EUR_ISIN)
    assert not isin_ok("US0378331006") and not isin_ok("US037833100") and not isin_ok("us0378331005")
