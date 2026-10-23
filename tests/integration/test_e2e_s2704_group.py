"""End to end, through the HTTP API: a group's natural catastrophe risk on S.27.01.04 (ITS (EU) 2023/894 Art. 34(1)(s),
Annex I; instructions Annex III S.27.01) under EIOPA's annual group entry point (arg).

  The group states, for the reporting period, each related undertaking's method of calculating group solvency (Directive
  2009/138/EC Art. 230 / 233; chosen per related undertaking, Del. Reg. (EU) 2015/35 Art. 328) — one person states it,
  another attests it. Refused: a method not on the closed list, a statement for an undertaking the group does not
  consolidate, one not stated for the group.
  not stated   the filing freezes the gap; no S.27.01.04 is exported, with the reason
  combination  Seguros by method 1, Iberia Re by method 2 → the template carries the method-1 part only (Annex III
               S.27.01 (b)): Iberia Re's book leaves the consolidated data → the form and workbook are S.27.01.04 → the
               XBRL instance is S.27.01.04 under arg, every fact with the group members; with EIOPA's package on hand,
               Arelle runs EIOPA's own rules and EIOPA's current list of switched-off group rules
  method 2     every undertaking by method 2 → S.27.01.04 does not apply (Annex III S.27.01 (c)): refused with the reason
  method 1     every undertaking by method 1 → the whole Art. 335 consolidated book, as before

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import io
import json
import os
import tempfile

import openpyxl
import pytest
from sqlalchemy import text

from tests.integration.money_method import state_method
from tests.integration.test_e2e_s2701 import (
    GROUP,
    IBERIA,
    IBERIA_RE,
    SEGUROS,
    _generate,
    _state,
    _test_lei,
    _users,
)

pytestmark = pytest.mark.integration
KEY = "group_solvency_method"


def _method(api, maker, checker, pe, member: str, value: str, entity: str | None = GROUP) -> None:
    """The group states one related undertaking's method; a second person attests it."""
    r = api.post("/v1/provided", headers=maker, json={"framework": "insurer_solvency", "datapoint_key": KEY, "value_text": value,
                                                      "breakdown_member": member, "reporting_entity_id": entity,
                                                      "reporting_period_end": pe.isoformat()})
    assert r.status_code == 201, r.text
    d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                 json={"decision": "approved", "reason": "per the group supervisor's decision"})
    assert d.status_code == 200, d.text


def _refused(resp, code: str) -> None:
    assert resp.status_code in (400, 409), resp.text
    assert resp.json()["error"]["error"] == code, resp.text


def test_the_group_reports_s2704_on_the_part_it_calculates_with_method_1(api):
    maker, checker, admin = _users(api)
    s = api.s
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, IBERIA)
    state_method(s, IBERIA, pe)
    _state(api, maker, checker, pe, {"ri_quota_share_pct": 50, "ri_xol_attachment_eur": 5_000_000,
                                     "ri_xol_limit_eur": 50_000_000}, GROUP)
    si = dict(s.execute(text("""SELECT reporting_entity_id::text, sum(primary_value_eur)::float FROM portfolio_entities
                                WHERE org_id = CAST(:o AS uuid) AND vertical = 'insurance' AND source = 'own' GROUP BY 1"""),
                        {"o": IBERIA}).all())
    assert si[SEGUROS] > 0 and si[IBERIA_RE] > 0

    # 1 · input refused at the door: a method off the list, an undertaking the group does not consolidate, not for a group
    base = {"framework": "insurer_solvency", "datapoint_key": KEY, "reporting_period_end": pe.isoformat()}
    _refused(api.post("/v1/provided", headers=maker, json={**base, "value_text": "method_3", "breakdown_member": SEGUROS,
                                                             "reporting_entity_id": GROUP}), "disclose.provided.choice")
    _refused(api.post("/v1/provided", headers=maker, json={**base, "value_text": "method_1", "breakdown_member": GROUP,
                                                             "reporting_entity_id": GROUP}), "disclose.provided.not_related")
    _refused(api.post("/v1/provided", headers=maker, json={**base, "value_text": "method_1", "breakdown_member": SEGUROS}),
             "disclose.provided.group_only")
    _refused(api.post("/v1/provided", headers=maker, json={**base, "value_text": "method_1", "reporting_entity_id": GROUP}),
             "disclose.provided.part_needed")

    # 2 · not stated: frozen as a gap, the form asks for it, no S.27.01.04 instance
    assert api.patch(f"/v1/filings/entities/{GROUP}", headers=admin, json={"lei": _test_lei("5299009IBERIAGROUP"),
                                                                          "set_lei": True}).status_code == 200
    fid, payload = _generate(api, maker, "insurer_solvency", GROUP)
    st = payload["_group_solvency"]
    assert st["status"] == "not_stated" and st["method"] is None
    assert st["not_stated"] == ["Iberia Mutual Seguros", "Iberia Re"]
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()["annex"]["sections"]
    sec = next(x for x in form if x.get("key") == KEY)
    assert [r["cells"][0]["text"] for r in sec["rows"]] == ["Iberia Mutual Seguros", "Iberia Re"]
    assert sec["rows"][0]["cells"][1]["supply"] == {"framework": "insurer_solvency", "key": KEY, "member": SEGUROS,
                                                    "choices": {"method_1": "Method 1 — accounting consolidation",
                                                                "method_2": "Method 2 — deduction and aggregation"},
                                                    "reporting_entity_id": GROUP}
    _refused(api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker), "filing.refused.xbrl_group_not_stated")

    # 3 · a combination: Seguros by method 1, Iberia Re by method 2 → the method-1 part only
    _method(api, maker, checker, pe, SEGUROS, "method_1")
    _method(api, maker, checker, pe, IBERIA_RE, "method_2")
    fid, payload = _generate(api, maker, "insurer_solvency", GROUP)
    st = payload["_group_solvency"]
    assert (st["status"], st["method"]) == ("complete", "combination") and st["excluded_from_template"] == [IBERIA_RE]
    assert {u["name"]: (u["method"], u["attested_by"]) for u in st["undertakings"]} == {
        "Iberia Mutual Seguros": ("method_1", "approver@iberia.demo"), "Iberia Re": ("method_2", "approver@iberia.demo")}
    assert payload["rollup"]["total_sum_insured_eur"] == pytest.approx(si[SEGUROS], rel=1e-6)      # Iberia Re's book left
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()["annex"]["sections"]
    natcat = [x for x in form if (x.get("spec") or {}).get("template")]
    assert natcat and all(x["spec"]["template"] == "S2704" and x["title"].startswith("S.27.01.04") for x in natcat)
    assert "Annex III" in natcat[0]["title"]
    wb = openpyxl.load_workbook(io.BytesIO(api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker).content))
    assert "S.27.01.04" in wb.sheetnames
    xb = api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker)
    assert xb.status_code == 200, xb.text
    _check_group_xbrl(xb.content)

    # 4 · method 2 for every related undertaking: S.27.01.04 does not apply
    _method(api, maker, checker, pe, SEGUROS, "method_2")
    fid, payload = _generate(api, maker, "insurer_solvency", GROUP)
    assert payload["_group_solvency"]["method"] == "method_2"
    _refused(api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker), "filing.refused.xbrl_group_method_two")

    # 5 · method 1 for every related undertaking: the whole consolidated book (Art. 335(1)(a) and (c))
    _method(api, maker, checker, pe, SEGUROS, "method_1")
    _method(api, maker, checker, pe, IBERIA_RE, "method_1")
    fid, payload = _generate(api, maker, "insurer_solvency", GROUP)
    assert payload["_group_solvency"]["method"] == "method_1" and payload["_group_solvency"]["excluded_from_template"] == []
    assert payload["rollup"]["total_sum_insured_eur"] == pytest.approx(si[SEGUROS] + 0.6 * si[IBERIA_RE], rel=1e-6)
    assert api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker).status_code == 200


def _check_group_xbrl(content: bytes) -> None:
    """S.27.01.04 under the group entry point, every dimensional fact with the two group members; with EIOPA's package
    held, EIOPA's own rules on it."""
    from lxml import etree
    doc = etree.fromstring(content)
    ns = {"xbrli": "http://www.xbrl.org/2003/instance", "link": "http://www.xbrl.org/2003/linkbase",
          "xlink": "http://www.w3.org/1999/xlink", "xbrldi": "http://xbrl.org/2006/xbrldi"}
    m = json.load(open("data/reference/eiopa/s2704_xbrl.2.8.2.json"))
    assert doc.find("link:schemaRef", ns).get("{http://www.w3.org/1999/xlink}href") == m["entry_point"]
    assert m["entry_point"].endswith("/mod/arg.xsd")
    for c in doc.iterfind("xbrli:context", ns):
        dims = {d.get("dimension"): d.text for d in c.iterfind(".//xbrldi:explicitMember", ns)}
        if dims:
            assert dims["s2c_dim:CM"] == "s2c_CS:x1" and dims["s2c_dim:SO"] == "s2c_SE:x44"
    if os.environ.get("XBRL_PACKAGES_DIR"):
        from scripts.validate_s2701_xbrl import validate
        with tempfile.NamedTemporaryFile("wb", suffix=".xbrl", delete=False) as t:
            t.write(content)
        res = validate(t.name)
        assert res["deactivations"] == "2026-06-03"                          # EIOPA's current list for the group entry point
        assert not res["instance_errors"] and not res["failed_in_scope"], res
        assert set(res["failed_needing_other_submodules"]) <= {"BV264_1-2"}   # needs man-made / other sub-modules
        assert len(res["evaluated"]) >= 12
