"""FX normalization — native-currency holdings convert to EUR at onboarding.

A mixed-currency book (USD/GBP/EUR lines) must roll up in EUR for SFDR, using the
ECB rate on-or-before the book's as-of date. Requires PostgreSQL.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.main import app
from core.db.session import get_session
from services.reference.fx import to_eur, FxError

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


@pytest.mark.integration
def test_to_eur_arithmetic_and_unknown_currency():
    with get_session() as s:
        # ECB 2023-12-29 seed: EUR per USD = 0.90580
        assert to_eur(s, 1_000_000, "USD", date(2024, 3, 1))["eur"] == 905_800.0
        assert to_eur(s, 1_000_000, "EUR", date(2024, 3, 1))["eur"] == 1_000_000.0
        # a date before any rate falls back to the earliest available, never guesses
        assert to_eur(s, 100, "GBP", date(1990, 1, 1))["source"] in ("ecb", "fallback")
        with pytest.raises(FxError):
            to_eur(s, 1, "ZZZ", date(2024, 3, 1))
        # a blank/None currency is unknown, NOT EUR (audit T9) — surfaced, never assumed 1.0
        with pytest.raises(FxError):
            to_eur(s, 1_000_000, None, date(2024, 3, 1))
        with pytest.raises(FxError):
            to_eur(s, 1_000_000, "  ", date(2024, 3, 1))


@pytest.mark.integration
def test_onboarding_converts_native_currency_and_stores_base():
    """A USD line onboarded stores its native value+currency and a converted EUR value."""
    created = {}
    with get_session() as s:
        fid = str(s.execute(text(
            "INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
            "VALUES (:o,'TEST FX Fund','fund','article_8') RETURNING fund_id"), {"o": DEMO_ORG}).scalar())
        iid = str(s.execute(text(
            "INSERT INTO issuers (name,issuer_type,country,source) "
            "VALUES ('FX Test Issuer','corporate','US','manual') RETURNING issuer_id")).scalar())
        # Pre-cache the security so resolve_isin is a cache hit (no GLEIF network call).
        s.execute(text(
            "INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
            "VALUES ('US00FXTEST01','FX Test Sec',:i,'equity','manual')"), {"i": iid})
        s.execute(text(
            "INSERT INTO issuer_facilities (issuer_id,name,latitude,longitude,country,source) "
            "VALUES (:i,'HQ',40.0,-74.0,'US','manual')"), {"i": iid})
        created = {"fid": fid, "iid": iid}

    try:
        client = TestClient(app)
        r = client.post(f"/v1/funds/{created['fid']}/holdings", json={
            "as_of_date": "2024-03-01",
            "holdings": [
                {"isin": "US00FXTEST01", "market_value": 1_000_000, "currency": "USD"},
            ],
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["positions_created"] == 1
        assert body["fx"]["converted_currencies"]["USD"]["rate"] == 0.9058
        assert not body["fx"]["errors"]

        with get_session() as s:
            row = s.execute(text(
                "SELECT market_value_eur, market_value_base, currency FROM fund_positions "
                "WHERE fund_id=:f"), {"f": created["fid"]}).mappings().first()
        assert float(row["market_value_eur"]) == 905_800.0   # converted
        assert float(row["market_value_base"]) == 1_000_000.0  # native preserved
        assert row["currency"] == "USD"
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": created["fid"]})
            s.execute(text("DELETE FROM securities WHERE isin='US00FXTEST01'"))
            s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": created["iid"]})
