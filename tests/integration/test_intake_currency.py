"""Multi-currency intake (phase 1 of the multi-currency review, decisions of 2026-09-26): an amount's currency and book
date are never assumed; balances convert at the closing rate on the book date, annual flows at the average of the 12
months to it; every rate used is reported; stale → a second person; no rate / unknown currency → the row is refused.
Service-level tests run as each sector's admin inside a rolled-back transaction."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import text

from services.intake import pipeline
from services.intake.catalog import TEMPLATES
from services.reference.fx import average_rate, rate_for
from tests.integration.test_intake_every_sector import _org_and_admin
from tests.integration.test_intake_pipeline import DECL, _csv, _rows

pytestmark = pytest.mark.integration
BOOK = date(2026, 6, 30)


def _bank(tag, n=3, **extra):
    return [{**r, "external_ref": f"{tag}-{i}", **extra} for i, r in enumerate(_rows(tag, n=n))]


def _stage(s, key, rows, currency="USD", book=BOOK):
    org_id, _ = _org_and_admin(s, TEMPLATES[key].org_type)
    df = pd.DataFrame(rows)
    return pipeline._run_controls(s, org_id, TEMPLATES[key], uuid.uuid4().hex, df, None,
                                  money_ctx={"currency": currency, "book_date": book, "field_currency": {}})


def test_undeclared_currency_or_book_date_is_refused_up_front(intake_client):
    raw = _csv(_rows("undeclared"))
    for data, needle in (({"book_date": "2026-06-30"}, "which currency"), ({"currency": "EUR"}, "book date"),
                         ({**DECL, "currency": "ZZZ"}, "not a currency"), ({**DECL, "book_date": "2999-01-01"}, "future")):
        r = intake_client.post("/v1/bank/assets/validate", headers=intake_client.maker,
                               files={"file": ("undeclared.csv", raw)}, data=data)
        assert r.status_code == 400 and needle in r.json()["error"]["message"], r.text


def test_api_push_must_declare_currency_and_book_date(intake_client):
    tok = intake_client.post("/v1/ingest/tokens", headers=intake_client.maker, json={"name": "TEST-PIPE-ccy"}).json()
    h = {"Authorization": f"Bearer {tok['raw_token']}"}
    try:
        r = intake_client.post("/v1/ingest/books/bank_assets", headers=h, json={"rows": _rows("apiccy", n=1)})
        assert r.status_code == 400 and "currency" in r.text
    finally:
        intake_client.delete(f"/v1/ingest/tokens/{tok['token_id']}", headers=intake_client.maker)


def test_balances_convert_at_the_closing_rate_of_the_book_date(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    ctl = _stage(s, "bank_assets", _bank(tag))
    r = rate_for(s, "USD", BOOK)
    used = [u for u in ctl["controls"]["currency"]["rates"] if u["currency"] == "USD"]
    assert used and all(u["policy"] == "closing" and u["book_date"] == "2026-06-30" for u in used)
    assert ctl["normalised"][0]["appraised_value_eur"] == pytest.approx(round(1_000_000 * r["rate"], 2))
    staged = ctl["staged"]["staged"][0]["record"]["_native"]
    assert staged["appraised_value_eur"] == [1_000_000.0, "USD"]          # the amount as sent is kept


def test_each_row_can_carry_its_own_currency(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    rows = _bank(tag)
    rows[0]["currency"], rows[1]["currency"], rows[2]["currency"] = "gbp", "EUR", None     # blank → the declared USD
    ctl = _stage(s, "bank_assets", rows)
    got = [n["appraised_value_eur"] for n in ctl["normalised"]]
    assert got == [pytest.approx(round(1e6 * rate_for(s, "GBP", BOOK)["rate"], 2)), 1_000_000.0,
                   pytest.approx(round(1e6 * rate_for(s, "USD", BOOK)["rate"], 2))]
    assert ctl["controls"]["currency"]["currencies"] == ["EUR", "GBP", "USD"]


def test_an_unknown_row_currency_refuses_the_row_never_falls_back(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    rows = _bank(tag, n=40)
    rows[0]["currency"] = "XXX"
    ctl = _stage(s, "bank_assets", rows)
    assert ctl["report"]["n_valid"] == 39
    assert any("no exchange rate for XXX" in p for e in ctl["report"]["errors"] for p in e["problems"])


def test_annual_flows_convert_at_the_period_average(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    rows = [{"property_name": f"TEST-CCY-{tag}-{i}", "latitude": 51.9 + i / 100, "longitude": 4.47, "property_value_eur": 10_000_000,
             "annual_noi_eur": 500_000, "property_type": "logistics", "external_ref": f"{tag}-{i}"} for i in range(3)]
    ctl = _stage(s, "realestate_properties", rows)
    n = ctl["normalised"][0]
    avg = average_rate(s, "USD", BOOK - timedelta(days=364), BOOK)
    assert n["annual_noi_eur"] == pytest.approx(round(500_000 * avg["rate"], 2))             # flow: average
    assert n["property_value_eur"] == pytest.approx(round(10_000_000 * rate_for(s, "USD", BOOK)["rate"], 2))   # balance
    policies = {u["policy"] for u in ctl["controls"]["currency"]["rates"]}
    assert policies == {"closing", "average"}


def test_a_stale_rate_needs_a_second_person(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    s.execute(text("DELETE FROM fx_rates WHERE ccy = 'XTS'"))
    s.execute(text("""INSERT INTO fx_rates (ccy, rate_date, eur_per_unit, units_per_eur, source, basis)
                      VALUES ('XTS', '2026-01-30', 0.1, 10, 'imf', 'month_end')"""))       # ~5 months before the book date
    ctl = _stage(s, "bank_assets", _bank(tag), currency="XTS")
    assert ctl["controls"]["gate"]["status"] == "needs_signoff"
    assert any(r.startswith("Currency:") and "XTS" in r for r in ctl["controls"]["gate"]["reasons"])


def test_a_future_row_book_date_is_refused(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    rows = _bank(tag, n=40)
    rows[0]["book_date"] = (date.today() + timedelta(days=30)).isoformat()
    ctl = _stage(s, "bank_assets", rows)
    assert ctl["report"]["n_valid"] == 39 and any("in the future" in p for e in ctl["report"]["errors"] for p in e["problems"])


def test_an_approval_replays_at_the_declared_currency_and_book_date(session_rolled_back):
    s, tag = session_rolled_back, uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, "bank")
    rows = _bank(tag, n=4) + [{**_bank(tag, n=1)[0], "asset_name": f"TEST-PIPE-{tag}-BAD", "latitude": 999, "external_ref": f"{tag}-X"}]
    out = pipeline.submit(s, org_id, "bank_assets", _csv(rows), f"{tag}.csv", user_id=user_id, currency="USD",
                          book_date="2026-06-30", reason="One bad row, rest current — please approve.")
    assert out["state"] == "awaiting_approval"
    b = s.execute(text("SELECT currency, book_date FROM ingest_batches WHERE batch_id = CAST(:b AS uuid)"),
                  {"b": out["batch_id"]}).one()
    assert (b[0], b[1]) == ("USD", BOOK)
    checker = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) AND user_id <> CAST(:u AS uuid) "
                             "LIMIT 1"), {"o": org_id, "u": user_id}).scalar()
    res = pipeline.decide(s, org_id, out["batch_id"], "approved", checker, "ok")
    assert res["state"] == "imported"
    v = s.execute(text("SELECT CAST(primary_value_eur AS FLOAT) FROM portfolio_entities WHERE external_ref = :r"),
                  {"r": f"{tag}-0"}).scalar()
    assert v == pytest.approx(round(1e6 * rate_for(s, "USD", BOOK)["rate"], 2))
