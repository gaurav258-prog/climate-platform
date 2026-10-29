"""End to end, through the HTTP API: a Pillar 3 ESG filing downloaded as the EBA's xBRL-CSV package for the Pillar 3
data hub (module ESGDIS 2.1.0, from reference date 31 March 2026).

  the reporting period set to 30 June 2026 → a filing prepared for the institution itself (a legal entity: individual,
  '.IND') → the package downloads under the EBA's file name and passes the EBA Filing Rules v5.8 for xBRL-CSV → with
  the EBA's packages held (XBRL_PACKAGES_DIR), Arelle finds no error against the EBA's taxonomy → a whole-organisation
  filing, which says neither individual nor consolidated, is refused the package with the reason

The API runs with its database session replaced by one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import os
import re

import pytest
from sqlalchemy import text

from services.governance.reporting_settings import upsert_reporting_settings
from tests.integration.conftest import login as _login
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration


def _lei(base18: str) -> str:
    """A test LEI with valid ISO 17442 check digits (a made-up entity, inside a rolled-back test)."""
    n = int("".join(str(int(c, 36)) for c in base18 + "00"))
    return f"{base18}{98 - n % 97:02d}"


def _file(api, maker, entity_id=None):
    q = f"&entity_id={entity_id}" if entity_id else ""
    token = api.get(f"/v1/filings/preflight?framework=bank_p3esg{q}", headers=maker).json()["confirm_token"]
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": token,
                                                     **({"entity_id": entity_id} if entity_id else {})})
    assert r.status_code == 201, r.text
    return r.json()["filing_id"]


def test_a_2026_pillar3_filing_downloads_as_the_ebas_data_hub_package(api, tmp_path):
    from scripts.validate_p3esg_xbrlcsv import filing_rules, validate
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    s = api.s
    upsert_reporting_settings(s, BANK_ORG, {"reporting_period_end": "2026-06-30"}, None)
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg' "
                   "AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    ent = s.execute(text("""SELECT e.entity_id::text, e.name FROM reporting_entities e WHERE e.org_id = CAST(:o AS uuid)
                            AND NOT EXISTS (SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = e.entity_id)
                            ORDER BY e.name LIMIT 1"""), {"o": BANK_ORG}).one()          # the institution itself: individual
    fid = _file(api, maker, ent.entity_id)
    r = api.get(f"/v1/filings/{fid}/export?format=xbrlcsv", headers=maker)          # no LEI of its own on file: refused
    assert r.status_code == 409 and r.json()["error"]["error"] == "filing.refused.xbrlcsv_entity_lei"
    lei = _lei("TESTLEI0P3XBRLCSV0")
    s.execute(text("UPDATE reporting_entities SET lei = :l, country = 'DE' WHERE entity_id = CAST(:e AS uuid)"),
              {"l": lei, "e": ent.entity_id})
    r = api.get(f"/v1/filings/{fid}/export?format=xbrlcsv", headers=maker)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip", r.text
    name = re.search(r'filename="([^"]+)"', r.headers["content-disposition"]).group(1)
    assert re.fullmatch(rf"{lei}\.IND_DE_PILLAR3020100_ESGDIS_2026-06-30_\d{{17}}\.zip", name), name
    path = tmp_path / name
    path.write_bytes(r.content)
    problems, m = filing_rules(str(path))
    assert problems == [] and m["module"]["version"] == "2.1.0"
    assert api.get(f"/v1/filings/{fid}/export?format=xbrlcsv", headers=maker).content == r.content   # the frozen bytes
    if os.environ.get("XBRL_PACKAGES_DIR"):
        res = validate(str(path))
        assert res["filing_rules"] == [] and res["xbrl_errors"] == [], res

    # the whole organisation of four entities is no filer of Pillar 3 ESG (CRR Arts 6(3), 13(1); E349): it is not offered,
    # and generating it is refused with the filers to choose from (a whole-organisation package: tests/unit/test_p3esg_xbrlcsv.py)
    pf = api.get("/v1/filings/preflight?framework=bank_p3esg", headers=maker).json()
    assert pf["needs_scope"] and pf["confirm_token"] is None
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": "x"})
    assert r.status_code == 409 and r.json()["error"]["error"] == "filing.refused.whole_org_no_filer"
    assert "Meridian Financial Group" in r.json()["error"]["detail"]["next"]
