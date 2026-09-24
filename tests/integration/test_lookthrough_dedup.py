"""Duplicate look-through endpoints deduped, and the surviving one's metadata bug fixed (2026-09-24 fix,
platform E2E audit finding #8): api/routers/funds.py had two endpoints doing the same job — POST
/funds/{id}/lookthrough (weight_pct-based) and POST /funds/{id}/look-through (market-value-based) — neither
reachable from the frontend, tests, or scripts (dead surface). The market-value one had the richer input
contract (the general `Holding` model), so it's kept; the weight_pct one is removed. While consolidating, a
real (if minor) correctness gap surfaced in the survivor: it hardcoded the new look-through sub-fund's
base_currency to 'EUR' and dropped sfdr_classification entirely, instead of inheriting both from the parent
fund — the removed endpoint got this right. Fixed by inheriting both.

Requires PostgreSQL. Non-polluting: rolls back its session (the DELETE of the wrapper position and the new
sub-fund insert never commit).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from core.db.session import get_session

AM_ORG = "44444444-4444-4444-8444-444444444444"   # Nordkap Asset Management (demo)
FUND_ID = "b5bf373d-b70b-4f65-87fb-11107bf93fa3"  # Nordkap Global Equity Fund — article_8, EUR
HELD_ISIN = "US0378331005"                        # Apple Inc., a real current position in that fund


@pytest.mark.integration
def test_lookthrough_subfund_inherits_parent_sfdr_classification_and_currency():
    from api.routers.funds import LookThroughBody, Holding, expand_look_through

    with get_session() as s:
        parent = s.execute(text("SELECT sfdr_classification, base_currency FROM funds WHERE fund_id = :f"),
                           {"f": FUND_ID}).mappings().first()
        assert parent["sfdr_classification"] == "article_8", "fixture assumption: Nordkap fund is Art. 8"

        body = LookThroughBody(isin=HELD_ISIN, constituents=[Holding(isin=HELD_ISIN, market_value_eur=1000.0)])
        result = expand_look_through(FUND_ID, body, s, AM_ORG)
        assert not result.get("error"), result

        child = s.execute(text("SELECT sfdr_classification, base_currency FROM funds WHERE fund_id = :f"),
                          {"f": result["sub_fund_id"]}).mappings().first()
        assert child["sfdr_classification"] == "article_8", \
            "look-through sub-fund must inherit the parent's SFDR classification, not drop it"
        assert child["base_currency"] == parent["base_currency"], \
            "look-through sub-fund must inherit the parent's base currency, not hardcode EUR"
        s.rollback()


@pytest.mark.integration
def test_duplicate_lookthrough_endpoint_is_gone():
    """The removed weight_pct-based POST /funds/{id}/lookthrough route must 404 now; the surviving
    /look-through route must still resolve (dispatched via a real request, not static route introspection —
    this FastAPI version wraps included routers opaquely on app.routes)."""
    from fastapi.testclient import TestClient
    from api.main import app

    with TestClient(app) as client:
        tok = client.post("/v1/auth/login", json={"email": "admin@nordkap.demo", "password": "Demo!admin1"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        r_old = client.post(f"/v1/funds/{FUND_ID}/lookthrough", json={"held_isin": HELD_ISIN, "constituents": []}, headers=headers)
        assert r_old.status_code == 404, f"removed endpoint should 404, got {r_old.status_code}: {r_old.text}"

        # the surviving endpoint resolves (may return a validation/business error for this payload, but
        # must NOT 404 — proving the route itself still exists)
        r_new = client.post(f"/v1/funds/{FUND_ID}/look-through", json={"isin": HELD_ISIN, "constituents": []}, headers=headers)
        assert r_new.status_code != 404, f"surviving endpoint must still resolve, got {r_new.status_code}"
