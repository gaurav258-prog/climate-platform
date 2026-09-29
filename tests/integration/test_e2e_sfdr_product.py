"""End to end, through the HTTP API: a fund's SFDR periodic template (RTS 2022/1288 Annex V, the governing version),
from its holdings and the manager's answers to the filed document.

  an Art. 9 fund with holdings in the reference period and an investee's own Taxonomy KPIs → the live document
  (computed items filled, the rest asked) → answers (a computed item, an unknown item and an out-of-range share
  refused) → another organisation cannot see it → the pre-filing check asks for the fund, then confirms its book →
  the filing freezes the fund as its subject (one live filing per fund and period) → the form shows the document →
  the checks count what is unanswered → HTML and JSON exports.

The API runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
NORDKAP = "44444444-4444-4444-8444-444444444444"


def _fund(s, period_end) -> str:
    from services.issuer_taxonomy import write_total
    fid = str(s.execute(text("""INSERT INTO funds (org_id, name, fund_type, sfdr_classification, lei)
                                VALUES (:o, 'E2E Impact Fund', 'fund', 'article_9', 'E2E00000000000IMPACT') RETURNING fund_id"""),
                        {"o": NORDKAP}).scalar())
    iid = str(s.execute(text("""INSERT INTO issuers (name, issuer_type, country, nace_code, source)
                                VALUES ('E2E Wind Operator', 'corporate', 'DK', '35.11', 'manual') RETURNING issuer_id""")).scalar())
    sid = str(s.execute(text("""INSERT INTO securities (isin, name, issuer_id, asset_class, source)
                                VALUES ('DK00E2EWIND1', 'E2E Wind', :i, 'equity', 'manual') RETURNING security_id"""), {"i": iid}).scalar())
    s.execute(text("""INSERT INTO fund_positions (fund_id, security_id, market_value_eur, weight_pct, as_of_date)
                      VALUES (:f, :s, 1000000, 100, :d)"""), {"f": fid, "s": sid, "d": period_end})
    write_total(s, iid, NORDKAP, period_end.year, "turnover", {"aligned": 80.0, "eligible": 95.0})
    return fid


def test_sfdr_periodic_from_holdings_and_answers_to_the_export(api):
    maker = _login(api, "admin@nordkap.demo", "Demo!admin1")
    other = _login(api, "admin@stellar.demo", "Demo!admin1")
    s = api.s
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, NORDKAP)
    fid = _fund(s, pe)

    # 1 · the live document: Annex V for an Art. 9 fund, computed items filled from the book
    d = api.get(f"/v1/funds/{fid}/sfdr-documents/periodic", headers=maker).json()
    assert d["template"] == "AV" and d["period_end"] == pe.isoformat()
    items = {i["id"]: i for i in d["items"]}
    assert items["product_name"]["value"] == {"text": "E2E Impact Fund"} and items["q_sust_obj.yes"]["value"] == {"ticked": True}
    assert items["table_top_inv"]["value"]["rows"][0]["table_top_inv.largest"] == "E2E Wind Operator"
    assert items["chart_tax_incl"]["value"]["graph"]["turnover"]["aligned"] == 80.0
    assert items["q_sio_met"]["status"] == "missing"

    # 2 · answers: one saved; a computed item, an unknown item and an out-of-range share refused, each with its reason
    r = api.put(f"/v1/funds/{fid}/sfdr-documents/periodic/answers", headers=maker, json={"answers": {
        "q_sio_met": {"text": "The objective was met: every investment is in renewable generation."},
        "product_name": {"text": "Renamed"}, "q_nope": {"text": "x"},
        "q_sust_obj.yes.env": {"ticked": True, "percent": 140}}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["saved"] == ["q_sio_met"]
    assert {x["item"] for x in body["refused"]} == {"product_name", "q_nope", "q_sust_obj.yes.env"}
    assert any("computed" in x["reason"] for x in body["refused"] if x["item"] == "product_name")

    # 3 · another organisation cannot read or answer it
    assert api.get(f"/v1/funds/{fid}/sfdr-documents/periodic", headers=other).status_code == 404
    assert api.put(f"/v1/funds/{fid}/sfdr-documents/periodic/answers", headers=other,
                   json={"answers": {"q_sio_met": {"text": "x"}}}).status_code == 404

    # 4 · the pre-filing check asks for the fund first, then confirms exactly its book
    ask = api.get("/v1/filings/preflight?framework=sfdr_periodic", headers=maker).json()
    assert ask["needs_fund"] and fid in {f["fund_id"] for f in ask["funds"]} and not ask["confirm_token"]
    pf = api.get(f"/v1/filings/preflight?framework=sfdr_periodic&fund_id={fid}", headers=maker).json()
    assert pf["fund"]["template"] == "AV" and pf["confirm_token"]
    wrong = api.get(f"/v1/filings/preflight?framework=sfdr_pai&fund_id={fid}", headers=maker)   # an entity-level report
    assert wrong.status_code == 409 and "not disclosed per financial product" in wrong.text

    # 5 · the filing freezes the fund as its subject; one live filing per fund and period
    g = api.post("/v1/filings", headers=maker, json={"framework": "sfdr_periodic", "confirm_token": pf["confirm_token"], "fund_id": fid})
    assert g.status_code == 201, g.text
    filing = g.json()
    assert filing["fund_id"] == fid and filing["filing_role"] == "product"
    again = api.post("/v1/filings", headers=maker, json={"framework": "sfdr_periodic", "confirm_token": pf["confirm_token"], "fund_id": fid})
    assert again.status_code == 409 and "already exists" in again.text

    # 6 · the form shows the document, frozen
    form = api.get(f"/v1/filings/{filing['filing_id']}/form", headers=maker).json()
    doc = next(sec for sec in form["annex"]["sections"] if sec.get("kind") == "document")
    frozen = {i["id"]: i for i in doc["items"]}
    assert frozen["q_sio_met"]["value"]["text"].startswith("The objective was met")
    assert frozen["chart_tax_incl"]["value"]["graph"]["turnover"]["aligned"] == 80.0

    # 7 · the checks count what is still unanswered (a warning, not a block)
    v = api.get(f"/v1/filings/{filing['filing_id']}/validation", headers=maker).json()
    ans = next(f for f in v["findings"] if f["rule"] == "items_answered")
    assert ans["severity"] == "warning" and not ans["passed"]

    # 8 · exports: the annex as a document, and the frozen record
    h = api.get(f"/v1/filings/{filing['filing_id']}/export?format=html", headers=maker)
    assert h.status_code == 200 and "E2E Impact Fund" in h.text and "renewable generation" in h.text and "[not yet answered]" in h.text
    j = api.get(f"/v1/filings/{filing['filing_id']}/export?format=json", headers=maker).json()
    assert j["payload"]["fund"]["fund_id"] == fid and j["payload"]["_specs"]["sfdr_product"]["version"]
