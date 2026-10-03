"""E144: a fund is created through the app (POST /v1/funds) — the manager states its name, type, SFDR article and base
currency (none defaulted); refused: a duplicate name, an unknown currency, a sub-portfolio without its fund (or a fund
with one), another organisation's parent, a malformed LEI; audited; read-only access cannot create one."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration


def test_a_manager_creates_a_fund_as_it_states_it(api):
    analyst = _login(api, "analyst@nordkap.demo", "Demo!analyst1")
    body = {"name": "Test Nordic Credit Fund", "fund_type": "fund", "sfdr_classification": "article_8", "base_currency": "sek"}
    for missing in ("sfdr_classification", "base_currency", "fund_type"):          # the manager's statements: required
        assert api.post("/v1/funds", headers=analyst, json={k: v for k, v in body.items() if k != missing}).status_code == 422
    assert api.post("/v1/funds", headers=analyst, json={**body, "sfdr_classification": "article_7"}).status_code == 422
    r = api.post("/v1/funds", headers=analyst, json={**body, "base_currency": "XYZ"})
    assert r.status_code == 422 and "ISO 4217" in r.text
    r = api.post("/v1/funds", headers=analyst, json={**body, "lei": "LEI0000000000000GOLD"})
    assert r.status_code == 422 and "not a valid LEI" in r.text

    r = api.post("/v1/funds", headers=analyst, json=body)
    assert r.status_code == 201, r.text
    f = r.json()
    assert (f["base_currency"], f["sfdr_classification"], f["lei"]) == ("SEK", "article_8", None)
    assert f["fund_id"] in {x["fund_id"] for x in api.get("/v1/funds", headers=analyst).json()["funds"]}
    assert api.s.execute(text("SELECT 1 FROM access_audit_log WHERE action = 'fund.created' AND target_id = :f"),
                         {"f": f["fund_id"]}).first()
    dup = api.post("/v1/funds", headers=analyst, json={**body, "name": "test nordic credit fund"})
    assert dup.status_code == 409 and "already exists" in dup.text

    sub = {**body, "name": "Test sleeve", "fund_type": "sub_portfolio"}
    assert api.post("/v1/funds", headers=analyst, json=sub).status_code == 422                        # names no fund
    assert api.post("/v1/funds", headers=analyst, json={**body, "name": "Other", "parent_fund_id": f["fund_id"]}).status_code == 422
    other_org = _login(api, "analyst@meridian.demo", "Demo!analyst1")
    assert api.post("/v1/funds", headers=other_org, json={**sub, "parent_fund_id": f["fund_id"]}).status_code == 404
    r = api.post("/v1/funds", headers=analyst, json={**sub, "parent_fund_id": f["fund_id"]})
    assert r.status_code == 201 and r.json()["parent_fund_id"] == f["fund_id"]
    assert api.post("/v1/funds", json=body).status_code in (401, 403)                                # not signed in


def test_a_complete_book_removes_what_was_sold_and_only_when_every_line_is_positioned(api):
    """E145: a holdings file stated as the complete book on its date removes that date's positions it does not list
    (audited, reported); with a line it cannot position, nothing changes. Without the statement a file adds/updates."""
    analyst = _login(api, "analyst@nordkap.demo", "Demo!analyst1")
    fid = api.post("/v1/funds", headers=analyst, json={"name": "Test book fund", "fund_type": "fund",
                                                       "sfdr_classification": "article_6", "base_currency": "EUR"}).json()["fund_id"]
    d = "2025-12-31"

    def up(isins, **kw):
        return api.post(f"/v1/funds/{fid}/holdings", headers=analyst, json={"as_of_date": d, **kw, "holdings": [
            {"isin": i, "market_value_eur": 1_000_000, "asset_class": "equity"} for i in isins]})

    def held():
        return set(api.s.execute(text("""SELECT s.isin FROM fund_positions p JOIN securities s USING (security_id)
                                         WHERE p.fund_id = CAST(:f AS uuid) AND p.as_of_date = :d"""), {"f": fid, "d": d}).scalars())
    assert up(["DE00ENERGY01", "NL00LOGIS001"]).status_code == 200
    r0 = up(["ES00FOODS001"])
    assert r0.status_code == 200 and isinstance(r0.json(), dict), r0.text[:600]
    assert r0.json()["positions_removed"] == [] and held() == {"DE00ENERGY01", "NL00LOGIS001", "ES00FOODS001"}
    bad = up(["ES00FOODS001", "NOT-AN-ISIN"], complete_book=True)
    assert bad.status_code == 422 and "nothing was changed" in bad.text and len(held()) == 3
    r = up(["ES00FOODS001"], complete_book=True)
    assert r.status_code == 200 and {x["isin"] for x in r.json()["positions_removed"]} == {"DE00ENERGY01", "NL00LOGIS001"}
    assert held() == {"ES00FOODS001"}
    assert api.s.execute(text("SELECT 1 FROM access_audit_log WHERE action = 'fund.positions_removed' AND target_id = :f"),
                         {"f": fid}).first()
