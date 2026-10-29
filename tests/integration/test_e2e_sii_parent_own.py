"""An insurance undertaking at the head of a group reports for itself and for the group (E348), end to end.

  ITS (EU) 2023/894 Art. 19(1)(s)(i) binds every insurance undertaking to its own S.27.01.01; Art. 34(1)(s) binds the
  participating undertaking to the group's S.27.01.04. Iberia, restructured in the test so Iberia Mutual Seguros heads
  the group (Iberia Re, 60 % proportional, below it):
  calendar  Seguros owes two reports — the group's, due 6 weeks later (Del. Reg. 2015/35 Art. 373), and its own — and
            Iberia Re its own; the pre-filing check offers all three
  values    a figure is stated for one of Seguros' reports and read by that report only (its own SCR and treaty, or the
            group's) — never borrowed across
  scope     its own report freezes its own book (no Iberia Re), recorded as the undertaking's S.27.01.01; the group's the
            consolidated book, recorded as S.27.01.04; both live at once, each matched to its own obligation; a second
            own report is refused while one is live; a refresh keeps the own book
  exports   the own report's XBRL is S.27.01.01 under EIOPA's solo entry point with Seguros' LEI; the group's is the
            group's template (refused with the reason while its method is not stated)
  refusals  a group's report for an entity with nothing below it; an own report of a parent for a report type that has
            none (a bank's Pillar 3); a role the obligation is not for

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.integration.money_method import state_method
from tests.integration.test_e2e_s2701 import IBERIA, IBERIA_RE, SEGUROS, _test_lei, _users

pytestmark = pytest.mark.integration
FW = "insurer_solvency"


def _state(api, maker, checker, pe, values: dict, entity: str, role: str):
    """Each value stated by the maker for one of the entity's reports and attested by the checker (four eyes)."""
    for key, v in values.items():
        r = api.post("/v1/provided", headers=maker, json={"framework": FW, "datapoint_key": key, "value_num": v,
                                                          "reporting_period_end": pe.isoformat(), "reporting_entity_id": entity,
                                                          "filing_role": role})
        assert r.status_code == 201, r.text
        d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                     json={"decision": "approved", "reason": "per the undertaking's Solvency II return"})
        assert d.status_code == 200, d.text


def _payload(api, maker, fid: str) -> dict:
    return json.loads(api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).content)["payload"]


def _attested(payload: dict) -> dict:
    return {p["key"].removeprefix("provided."): p["value"] for p in payload["_provided_attested"]}


def _refused(resp, code: str) -> None:
    assert resp.status_code == 409, resp.text
    assert resp.json()["error"]["error"] == code, resp.text


def test_an_undertaking_at_the_head_of_a_group_reports_for_itself_and_for_the_group(api):
    maker, checker, admin = _users(api)
    s = api.s
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, IBERIA)
    state_method(s, IBERIA, pe)
    # Seguros heads the group: Iberia Re (60 %, proportional) below it; the group node above nothing any more
    s.execute(text("UPDATE reporting_entities SET parent_entity_id = NULL, lei = :l WHERE entity_id = CAST(:e AS uuid)"),
              {"e": SEGUROS, "l": _test_lei("5493001SEGUROSTST1")})
    s.execute(text("UPDATE reporting_entities SET parent_entity_id = CAST(:p AS uuid) WHERE entity_id = CAST(:e AS uuid)"),
              {"e": IBERIA_RE, "p": SEGUROS})
    si = dict(s.execute(text("""SELECT reporting_entity_id::text, sum(primary_value_eur)::float FROM portfolio_entities
                                WHERE org_id = CAST(:o AS uuid) AND vertical = 'insurance' AND source = 'own' GROUP BY 1"""),
                        {"o": IBERIA}).all())
    n = dict(s.execute(text("""SELECT reporting_entity_id::text, count(*) FROM portfolio_entities
                               WHERE org_id = CAST(:o AS uuid) AND vertical = 'insurance' AND source = 'own' GROUP BY 1"""),
                       {"o": IBERIA}).all())

    # 1 · the calendar owes Seguros two reports — the group's 6 weeks after its own — and Iberia Re its own
    def owed() -> dict:
        cal = api.get("/v1/obligations", headers=maker).json()["obligations"]
        return {(o["entity_id"], o["filing_role"]): o for o in cal if o["framework"] == FW and o["period_end"] == pe.isoformat()}
    ob = owed()
    assert set(ob) == {(SEGUROS, "consolidated"), (SEGUROS, "solo"), (IBERIA_RE, "solo")}
    assert all(o["scope_role"] == role for (_, role), o in ob.items())          # the role the prepare dialog sends
    assert (date.fromisoformat(ob[(SEGUROS, "consolidated")]["due_date"])
            - date.fromisoformat(ob[(SEGUROS, "solo")]["due_date"])) == timedelta(weeks=6)
    pf = api.get(f"/v1/filings/preflight?framework={FW}", headers=maker).json()
    assert pf["needs_scope"] and pf["scopes"] == [
        {"entity_id": SEGUROS, "name": "Iberia Mutual Seguros", "role": "consolidated"},
        {"entity_id": SEGUROS, "name": "Iberia Mutual Seguros", "role": "solo"},
        {"entity_id": IBERIA_RE, "name": "Iberia Re", "role": "solo"}]

    # 2 · each report's figures stated for it: Seguros' own SCR and treaty, and the group's
    _state(api, maker, checker, pe, {"scr_total": 100_000_000, "ri_quota_share_pct": 10}, SEGUROS, "solo")
    _state(api, maker, checker, pe, {"scr_total": 300_000_000, "ri_quota_share_pct": 50}, SEGUROS, "consolidated")
    from services.insurer_capital import position, programme
    assert position(s, IBERIA, pe, SEGUROS, "solo")["scr_total"] == 100_000_000
    assert position(s, IBERIA, pe, SEGUROS)["scr_total"] == 300_000_000          # a parent's own role: the group's
    assert programme(s, IBERIA, pe, SEGUROS, "solo")[0]["quota_share_pct"] == 10.0

    # 3 · the pre-filing check of each: its own book, or the group's consolidated book
    own_pf = api.get(f"/v1/filings/preflight?framework={FW}&entity_id={SEGUROS}&filing_role=solo", headers=maker).json()
    grp_pf = api.get(f"/v1/filings/preflight?framework={FW}&entity_id={SEGUROS}", headers=maker).json()
    assert own_pf["filing_role"] == "solo" and grp_pf["filing_role"] == "consolidated"
    assert own_pf["coverage"]["total"] == n[SEGUROS] and grp_pf["coverage"]["total"] == n[SEGUROS] + n[IBERIA_RE]
    assert own_pf["confirm_token"] != grp_pf["confirm_token"]

    # 4 · Seguros' own report, prepared for its obligation: its own book, its own figures, the undertaking's S.27.01.01
    g = api.post("/v1/filings", headers=maker, json={"framework": FW, "confirm_token": own_pf["confirm_token"],
                                                     "obligation_id": ob[(SEGUROS, "solo")]["obligation_id"]})
    assert g.status_code == 201, g.text
    own = g.json()
    assert own["filing_role"] == "solo" and own["entity_id"] == SEGUROS
    p = _payload(api, maker, own["filing_id"])
    assert p["_filer"] == {"level": "undertaking", "entity_id": SEGUROS, "template": "S.27.01.01",
                           "basis": "Implementing Regulation (EU) 2023/894 Art. 19(1)(s)(i)"}
    assert p["_scope"] == {"reporting_entity_id": SEGUROS, "filing_role": "solo"} and "_group_solvency" not in p
    assert p["rollup"]["total_sum_insured_eur"] == pytest.approx(si[SEGUROS], rel=1e-6)      # no Iberia Re in it
    assert _attested(p)["scr_total"] == 100_000_000 and _attested(p)["ri_quota_share_pct"] == 10
    assert p["s2701"]["standard_formula_natcat"]["treaty_basis"] == "attested"

    # 5 · the group's report beside it: the consolidated book (Art. 335(1)(a), (c)), the group's figures, S.27.01.04
    g = api.post("/v1/filings", headers=maker, json={"framework": FW, "confirm_token": grp_pf["confirm_token"],
                                                     "obligation_id": ob[(SEGUROS, "consolidated")]["obligation_id"]})
    assert g.status_code == 201, g.text
    grp = g.json()
    assert grp["filing_role"] == "consolidated"
    assert date.fromisoformat(grp["due_date"]) - date.fromisoformat(own["due_date"]) == timedelta(weeks=6)
    assert "Art. 373" in grp["due_rule"] and "Art. 373" not in own["due_rule"]
    q = _payload(api, maker, grp["filing_id"])
    assert q["_filer"]["level"] == "group" and q["_filer"]["template"] == "S.27.01.04"
    assert q["_scope"] == {"reporting_entity_id": SEGUROS, "filing_role": "consolidated"}
    assert q["rollup"]["total_sum_insured_eur"] == pytest.approx(si[SEGUROS] + 0.6 * si[IBERIA_RE], rel=1e-6)
    assert _attested(q)["scr_total"] == 300_000_000 and _attested(q)["ri_quota_share_pct"] == 50

    # 6 · both live, each the answer to its own obligation; a second own report is refused while one is live
    ob = owed()
    assert ob[(SEGUROS, "solo")]["filing_id"] == own["filing_id"]
    assert ob[(SEGUROS, "consolidated")]["filing_id"] == grp["filing_id"] and ob[(IBERIA_RE, "solo")]["filing_id"] is None
    again = api.get(f"/v1/filings/preflight?framework={FW}&entity_id={SEGUROS}&filing_role=solo", headers=maker).json()
    assert not again["can_generate"] and again["existing_status"] == "draft"
    _refused(api.post("/v1/filings", headers=maker, json={"framework": FW, "confirm_token": again["confirm_token"],
                                                          "entity_id": SEGUROS, "filing_role": "solo"}),
             "filing.refused.already_live")

    # 7 · the own report's template is the undertaking's: S.27.01.01 under EIOPA's solo entry point, Seguros' LEI; the
    #     group's is the group's (its method not stated: refused with the reason)
    x = api.get(f"/v1/filings/{own['filing_id']}/export?format=xbrl", headers=maker)
    assert x.status_code == 200, x.text
    from lxml import etree
    doc = etree.fromstring(x.content)
    entry = json.load(open("data/reference/eiopa/s2701_xbrl.2.8.2.json"))["entry_point"]
    assert doc.find("{http://www.xbrl.org/2003/linkbase}schemaRef").get("{http://www.w3.org/1999/xlink}href") == entry
    assert {e.text for e in doc.iter("{http://www.xbrl.org/2003/instance}identifier")} == {_test_lei("5493001SEGUROSTST1")}
    _refused(api.get(f"/v1/filings/{grp['filing_id']}/export?format=xbrl", headers=maker), "filing.refused.xbrl_group_not_stated")

    # 8 · a refresh keeps the own book; the form's entered cells are stated for the own report
    assert api.post(f"/v1/filings/{own['filing_id']}/refresh", headers=maker).status_code == 200
    p = _payload(api, maker, own["filing_id"])
    assert p["_scope"]["filing_role"] == "solo" and p["rollup"]["total_sum_insured_eur"] == pytest.approx(si[SEGUROS], rel=1e-6)
    form = api.get(f"/v1/filings/{own['filing_id']}/form", headers=maker).json()
    assert form["filing_role"] == "solo"
    supplies = [c["supply"] for sec in form["annex"]["sections"] for r in sec.get("rows", []) for c in r.get("cells", [])
                if isinstance(c, dict) and c.get("supply")]
    assert supplies and {(x["reporting_entity_id"], x["filing_role"]) for x in supplies} == {(SEGUROS, "solo")}

    # 9 · refusals: a role the obligation is not for; a group's report for an entity with nothing below it
    _refused(api.post("/v1/filings", headers=maker, json={"framework": FW, "confirm_token": "x", "filing_role": "consolidated",
                                                          "obligation_id": ob[(IBERIA_RE, "solo")]["obligation_id"]}),
             "filing.refused.obligation_other_entity")
    _refused(api.get(f"/v1/filings/preflight?framework={FW}&entity_id={IBERIA_RE}&filing_role=consolidated", headers=maker),
             "filing.refused.role_scope")
    r = api.post("/v1/provided", headers=maker, json={"framework": FW, "datapoint_key": "scr_total", "value_num": 1,
                                                      "reporting_period_end": pe.isoformat(), "reporting_entity_id": IBERIA_RE,
                                                      "filing_role": "consolidated"})
    assert r.status_code == 400 and r.json()["error"]["error"] == "disclose.provided.role", r.text


def test_an_own_report_of_a_parent_is_offered_only_where_the_regulation_asks_for_it(session_rolled_back):
    """A bank group's top files its consolidated report (the calendar's role for it stays its own); an own-book report of
    a parent is refused for a report type other than Solvency II nat-cat — it would be built on no text."""
    s = session_rolled_back
    from services.governance import filings as F
    org, top = s.execute(text("""SELECT e.org_id::text, e.entity_id::text FROM reporting_entities e
                                 WHERE e.name = 'Meridian Financial Group'""")).one()
    with pytest.raises(F.FilingError) as e:
        F.preflight(s, org, "bank", "bank_p3esg", top, filing_role="solo")
    assert e.value.code == "filing.refused.own_book_not_offered"
    assert F._scope_role(s, org, "bank_p3esg", top, None) == "consolidated"
    # the calendar's generic row for it is labelled 'solo', but no role tells a bank report's scope apart: the dialog
    # prepares it as before (its role from the tree)
    cal = [o for o in F.list_obligations(s, org, "bank") if o["entity_id"] == top]
    assert cal and all(o["scope_role"] is None for o in cal)
