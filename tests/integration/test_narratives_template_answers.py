"""The two narrative stores that used to live on organizations are template answers (narratives_answers_20260930),
through the HTTP API with unchanged response shapes:

  Pillar 3 ESG qualitative Tables 1-3 → family bank_p3esg, document qualitative (a blank text clears a row)
  (the SFDR PAI statement's sections are answered per reference period: test_e2e_sfdr_pai_statement.py)

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
    """Text belongs to one institution and one reference date (default: the organisation, its reporting period end)."""
    from services.governance.filings import reporting_period_end
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    pe = reporting_period_end(api.s, BANK_ORG)
    r = api.patch("/v1/filings/qualitative/p3esg", headers=maker, json={"values": {"table1.a": "  Business strategy text.  "}})
    assert r.status_code == 200, r.text
    rows = {x["key"]: x["value"] for t in r.json()["tables"] for x in t["rows"]}
    assert rows["table1.a"] == "Business strategy text." and r.json()["period_end"] == pe.isoformat()
    assert T.read(api.s, BANK_ORG, "bank_p3esg", "qualitative", period_end=pe)["table1.a"] == {"text": "Business strategy text."}
    earlier = T.read(api.s, BANK_ORG, "bank_p3esg", "qualitative").get("table1.a")             # not organisation-wide
    assert earlier != {"text": "Business strategy text."}

    other = api.get(f"/v1/filings/qualitative/p3esg?period_end={pe.year - 1}-12-31", headers=maker).json()
    assert {x["key"]: x["value"] for t in other["tables"] for x in t["rows"]}["table1.a"] == ""   # another reference date
    bad = api.get("/v1/filings/qualitative/p3esg?undertaking=00000000-0000-0000-0000-000000000001", headers=maker)
    assert bad.status_code == 422

    r = api.patch("/v1/filings/qualitative/p3esg", headers=maker, json={"values": {"table1.a": ""}})
    assert r.status_code == 200
    assert "table1.a" not in T.read(api.s, BANK_ORG, "bank_p3esg", "qualitative", period_end=pe)
    got = api.get("/v1/filings/qualitative/p3esg", headers=maker).json()
    assert {x["key"]: x["value"] for t in got["tables"] for x in t["rows"]}["table1.a"] == ""
    assert {"tables", "total_rows", "authored", "spec", "entity_id", "period_end", "earlier"} == set(got)
