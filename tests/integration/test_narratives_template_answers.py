"""The two narrative stores that used to live on organizations are template answers (narratives_answers_20260930),
through the HTTP API with unchanged response shapes:

  Pillar 3 ESG qualitative Tables 1-3 → family bank_p3esg, document qualitative (a blank text clears a row)
  the SFDR PAI statement's narrative sections → family sfdr_pai, document pai_statement (a save replaces the set;
  an unknown section is refused and nothing is written), which the statement's filing readiness reads.

The API runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import pytest

from services.governance import template_answers as T
from tests.integration.conftest import login as _login
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
NORDKAP = "44444444-4444-4444-8444-444444444444"


def test_pillar3_qualitative_text_is_a_template_answer(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    r = api.patch("/v1/filings/qualitative/p3esg", headers=maker, json={"values": {"table1.a": "  Business strategy text.  "}})
    assert r.status_code == 200, r.text
    rows = {x["key"]: x["value"] for t in r.json()["tables"] for x in t["rows"]}
    assert rows["table1.a"] == "Business strategy text."
    assert T.read(api.s, BANK_ORG, "bank_p3esg", "qualitative")["table1.a"] == {"text": "Business strategy text."}

    r = api.patch("/v1/filings/qualitative/p3esg", headers=maker, json={"values": {"table1.a": ""}})
    assert r.status_code == 200
    assert "table1.a" not in T.read(api.s, BANK_ORG, "bank_p3esg", "qualitative")
    got = api.get("/v1/filings/qualitative/p3esg", headers=maker).json()
    assert {x["key"]: x["value"] for t in got["tables"] for x in t["rows"]}["table1.a"] == ""
    assert set(got) == {"tables", "total_rows", "authored", "spec"}


def test_sfdr_pai_narratives_are_template_answers(api, monkeypatch):
    from api.routers import funds as F
    from ml.regulatory.sfdr_pai import entity_pai_statement
    from services.reference.gleif import GleifRecord
    monkeypatch.setattr(F.gleif, "fetch_lei", lambda lei: GleifRecord(lei=lei, name="Nordkap AM", entity_status="ACTIVE", country="NO"))
    maker = _login(api, "admin@nordkap.demo", "Demo!admin1")
    lei = "5299000NORDKAPAM0001"

    narratives = {"policies": "PAI policy.", "actions": "Engaged 12 issuers.", "engagement": "Stewardship code."}
    r = api.put("/v1/manager/filing-profile", headers=maker, json={"lei": lei, "narratives": narratives})
    assert r.status_code == 200, r.text
    prof = api.get("/v1/manager/filing-profile", headers=maker).json()
    assert prof["sfdr_narratives"] == narratives                      # 'standards' left out → cleared
    assert {"name", "legal_name", "lei", "filing_contact_email", "country"} <= set(prof)

    # a narratives save re-sends the same LEI alone: the manager's legal name on file is kept, not replaced by GLEIF's
    api.put("/v1/manager/filing-profile", headers=maker, json={"lei": lei, "legal_name": "Nordkap Asset Management"})
    r = api.put("/v1/manager/filing-profile", headers=maker, json={"lei": lei, "narratives": narratives})
    assert r.status_code == 200
    assert api.get("/v1/manager/filing-profile", headers=maker).json()["legal_name"] == "Nordkap Asset Management"

    r = api.put("/v1/manager/filing-profile", headers=maker, json={"lei": lei, "narratives": {**narratives, "bogus": "x"}})
    assert r.status_code == 422
    assert T.read(api.s, NORDKAP, "sfdr_pai", "pai_statement") == {k: {"text": v} for k, v in narratives.items()}

    stmt = entity_pai_statement(api.s, NORDKAP)
    if not stmt.get("error"):
        assert stmt["narratives"]["policies"] == "PAI policy." and stmt["narratives"]["standards"] is None
        cs = stmt["coverage_summary"]                     # indicators not computed: the best efforts are asked (E83)
        expect = [] if cs["computed"] == cs["mandatory_indicators"] else [
            "details of the best efforts used to obtain the information not readily available (RTS 2022/1288 Art. 7(2))"]
        assert stmt["narratives"]["missing"] == expect
