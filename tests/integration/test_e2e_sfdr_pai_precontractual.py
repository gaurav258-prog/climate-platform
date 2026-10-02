"""End to end through the HTTP API, in one rolled-back transaction (Nordkap Asset Management; maker / checker):

  (the entity's PAI statement, RTS 2022/1288 Annex I, per reference period: test_e2e_sfdr_pai_statement.py)
  pre-contractual document (Annex II, an Art. 8 fund)
    the live template → an answer → the filing freezes the fund as its subject → the form shows the document → the
    unanswered items counted → HTML annex → four eyes, attestation, submission
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
NORDKAP = "44444444-4444-4444-8444-444444444444"
LEI = "9695003YCOLOMW6OMD54"


def _users(api):
    return _login(api, "analyst@nordkap.demo", "Demo!analyst1"), _login(api, "approver@nordkap.demo", "Demo!approve1")


def _set_aside(s, framework):
    """A live filing of this report may already exist in the demo data: set it aside inside the rolled-back transaction."""
    s.execute(text("ALTER TABLE regulatory_filing DISABLE TRIGGER USER"))
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = :f"),
              {"o": NORDKAP, "f": framework})
    s.execute(text("ALTER TABLE regulatory_filing ENABLE TRIGGER USER"))


def _file_and_submit(api, maker, checker, fid, statement):
    sr = api.post(f"/v1/filings/{fid}/submit-for-review", headers=maker)
    assert sr.status_code == 200, sr.text
    rid = sr.json()["approval_request_id"]
    assert api.post(f"/v1/approvals/{rid}/decide", headers=maker, json={"decision": "approved"}).status_code in (403, 422)
    d = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": "reviewed"})
    assert d.status_code == 200, d.text
    at = api.post(f"/v1/filings/{fid}/attest", headers=checker, json={"statement": statement})
    assert at.status_code == 200, at.text
    sub = api.post(f"/v1/filings/{fid}/submit", headers=maker, json={"submission_ref": "NCA-SFDR-E2E"})
    assert sub.status_code == 200, sub.text


def test_an_art8_fund_files_its_precontractual_document(api):
    maker, checker = _users(api)
    s = api.s
    fid = str(s.execute(text("""INSERT INTO funds (org_id, name, fund_type, sfdr_classification, lei)
                                VALUES (:o, 'E2E Transition Fund', 'fund', 'article_8', 'E2E0000000000TRANSIT') RETURNING fund_id"""),
                        {"o": NORDKAP}).scalar())
    d = api.get(f"/v1/funds/{fid}/sfdr-documents/precontractual", headers=maker)
    assert d.status_code == 200, d.text
    doc = d.json()
    assert doc["template"] == "AII"
    items = {i["id"]: i for i in doc["items"]}
    assert items["product_name"]["value"] == {"text": "E2E Transition Fund"}
    ask = next(i for i in doc["items"] if i["status"] == "missing" and i["kind"] == "question")
    r = api.put(f"/v1/funds/{fid}/sfdr-documents/precontractual/answers", headers=maker,
                json={"answers": {ask["id"]: {"text": "Answered by the E2E test."}}})
    assert r.status_code == 200 and r.json()["saved"] == [ask["id"]], r.text

    pf = api.get(f"/v1/filings/preflight?framework=sfdr_precontractual&fund_id={fid}", headers=maker).json()
    assert pf["confirm_token"]
    g = api.post("/v1/filings", headers=maker, json={"framework": "sfdr_precontractual", "confirm_token": pf["confirm_token"],
                                                     "fund_id": fid})
    assert g.status_code == 201, g.text
    filing = g.json()
    assert filing["fund_id"] == fid and filing["filing_role"] == "product"
    form = api.get(f"/v1/filings/{filing['filing_id']}/form", headers=maker).json()
    frozen = {i["id"]: i for sec in form["annex"]["sections"] if sec.get("kind") == "document" for i in sec["items"]}
    assert frozen[ask["id"]]["value"]["text"] == "Answered by the E2E test."
    v = api.get(f"/v1/filings/{filing['filing_id']}/validation", headers=maker).json()
    assert v["passed"], [f for f in v["findings"] if not f["passed"] and f["severity"] == "blocking"]
    assert any(f["rule"] == "items_answered" and not f["passed"] for f in v["findings"])     # the rest still unanswered
    h = api.get(f"/v1/filings/{filing['filing_id']}/export?format=html", headers=maker)
    assert h.status_code == 200 and "E2E Transition Fund" in h.text and "Answered by the E2E test." in h.text
    _file_and_submit(api, maker, checker, filing["filing_id"], "I approve the pre-contractual disclosure.")
