"""Who files the bank and building-owner reports (services.governance.report_filers, E349), end to end.

  Pillar 3 ESG  CRR: Part Eight on an individual basis (Art. 6(1)), but not for a parent or a subsidiary (Art. 6(3)); an
                EU parent on its consolidated situation (Art. 13(1), first subparagraph); a large subsidiary its own
                (second subparagraph). calendar: none or one entity — the organisation; two tops side by side — each its
                own; a group above them — the group only; a subsidiary stated large (four eyes) — its own too, on its
                sub-consolidated situation when it has entities below it; a branch never
  Taxonomy      Delegated Regulation (EU) 2021/2178 Art. 1(8), (9): the undertakings of Directive 2013/34/EU Arts 19a, 29a.
                calendar: no role stated — none owed, the undertakings listed to state their role, a supervisor's date
                kept; a role stated — owed, the supervisor's date carried onto it; an exempt subsidiary — none owed,
                its scope refused
  Meridian      (four entities) through the API: the group is owed Pillar 3; the whole organisation is refused with the
                filers; the group's filing records its filer and states its subsidiaries' size class on its form; a
                subsidiary stated large is owed its own; a whole-organisation filing frozen before exports no template
  Stellar       (three entities): an exempt subsidiary's Taxonomy scope is refused with its parent's report

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login
from tests.integration.filers import group, state_role
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
STELLAR = "33333333-3333-4333-8333-333333333333"


def _refused(resp, code: str) -> dict:
    assert resp.status_code == 409, resp.text
    body = resp.json()["error"]
    assert body["error"] == code, resp.text
    return body


class _Org:
    """A bank of its own inside the transaction, with the calendar read for one report and period."""

    def __init__(self, s, fw: str):
        from services.governance import filings as F
        self.s, self.fw, self.F = s, fw, F
        self.id = str(uuid.uuid4())
        s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (CAST(:o AS uuid), :n, 'bank', 'DE')"),
                  {"o": self.id, "n": f"Filers test {self.id[:8]}"})
        self.pe = F.reporting_period_end(s, self.id)
        # two people of the demo bank act as maker and checker of this test bank's statements
        self.maker, self.checker = s.execute(text("""SELECT user_id::text FROM users WHERE email IN
            ('admin@meridian.demo', 'approver@meridian.demo') ORDER BY email""")).scalars().all()

    def entity(self, name: str, parent: str | None = None, kind: str = "legal_entity", solo: bool = True) -> str:
        eid = str(uuid.uuid4())
        self.s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name, kind, parent_entity_id, requires_solo_filing)
                               VALUES (CAST(:e AS uuid), CAST(:o AS uuid), :n, :k, CAST(:p AS uuid), :solo)"""),
                       {"e": eid, "o": self.id, "n": name, "k": kind, "p": parent, "solo": solo})
        return eid

    def owed(self, period_end: date | None = None) -> set:
        self.F.ensure_obligations(self.s, self.id, "bank")
        return {(r[0], r[1], r[2]) for r in self.s.execute(text("""
            SELECT entity_id::text, filing_role, source FROM regulatory_obligation
            WHERE org_id = CAST(:o AS uuid) AND framework = :f AND period_end = :pe"""),
            {"o": self.id, "f": self.fw, "pe": period_end or self.pe}).all()}

    def state_large(self, subsidiary: str, value: str = "large") -> None:
        from services.governance import provided_data as P
        r = P.submit(self.s, self.id, self.maker, framework="bank_p3esg", datapoint_key="large_institution",
                     value_text=value, breakdown_member=subsidiary, reporting_period_end=self.pe.isoformat())
        P.attest(self.s, self.id, {"provided_id": r["provided_id"]}, "approved", self.checker)

    def state_role(self, entity: str, role: str, **parent) -> None:
        from services.governance.csrd_roles import apply_decision, request_role
        req = request_role(self.s, self.id, self.maker, entity_id=entity, period_end=self.pe, role=role, **parent)
        apply_decision(self.s, self.id, req["approval_request_id"],
                       {"entity_id": entity, "period_end": self.pe.isoformat(), "role": role, **parent}, "approved",
                       self.checker)


def test_pillar3_is_owed_by_the_eu_parent_a_large_subsidiary_and_an_institution_on_its_own(session_rolled_back):
    s = session_rolled_back
    org = _Org(s, "bank_p3esg")
    pe = org.pe
    assert {(e, r) for e, r, _ in org.owed()} == {(None, "whole_org")}                 # no entity: the organisation
    alpha = org.entity("Alpha Bank")
    assert {(e, r) for e, r, _ in org.owed()} == {(None, "whole_org"), (alpha, "solo")}

    # a supervisor's date for the period before, set for the organisation (it was the institution)
    prev = date(pe.year - 1, 12, 31)
    s.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, source, set_by, filing_role)
                      VALUES (CAST(:o AS uuid), 'bank_p3esg', :pe, :pl, :due, 'supervisor', 'Test supervisor', 'whole_org')"""),
              {"o": org.id, "pe": prev, "pl": f"FY{prev.year}", "due": date(pe.year, 4, 30)})

    # a second institution side by side, neither parent nor subsidiary: each discloses its own (Art. 6(1))
    beta = org.entity("Beta Bank")
    assert {(e, r) for e, r, _ in org.owed()} == {(alpha, "solo"), (beta, "solo")}
    assert {(e, r) for e, r, _ in org.owed(prev)} == {(alpha, "solo"), (beta, "solo")}    # the supervisor's date carried

    # a group above both: the EU parent on its consolidated situation only — a subsidiary owes no individual
    # disclosure (Art. 6(3)), a branch never
    top = org.entity("Alpha Group", kind="group", solo=False)
    s.execute(text("UPDATE reporting_entities SET parent_entity_id = CAST(:t AS uuid) WHERE entity_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
              {"t": top, "a": alpha, "b": beta})
    branch = org.entity("Alpha Bank, Paris branch", parent=alpha, kind="branch", solo=False)
    assert {(e, r) for e, r, _ in org.owed()} == {(top, "consolidated")}

    # Alpha stated a large institution (four eyes): it discloses its own, on its sub-consolidated situation (the branch
    # below it); Beta stated not large owes nothing
    org.state_large(alpha)
    org.state_large(beta, "not_large")
    assert {(e, r) for e, r, _ in org.owed()} == {(top, "consolidated"), (alpha, "consolidated")}
    from services.governance import crr_filers
    with pytest.raises(ValueError):
        crr_filers.check_member(s, org.id, branch)                    # a branch is no subsidiary to state
    with pytest.raises(ValueError):
        crr_filers.check_member(s, org.id, top)                       # nor is the group's top

    # the filer records: the group lists its subsidiaries with their stated size class
    from services.governance.report_filers import record
    g = record(s, org.id, "bank_p3esg", top, True, pe)
    assert g["level"] == "group" and "Art. 13(1), first subparagraph" in g["basis"]
    assert {x["name"]: x["stated"] for x in g["subsidiaries"]} == {"Alpha Bank": "large", "Beta Bank": "not_large"}
    assert record(s, org.id, "bank_p3esg", alpha, True, pe)["level"] == "large_subsidiary"
    assert record(s, org.id, "bank_p3esg", beta, False, pe)["level"] == "not_owed"


def test_the_taxonomy_kpis_are_owed_by_each_undertaking_stated_to_report(session_rolled_back):
    s = session_rolled_back
    org = _Org(s, "bank_tcfd")
    from services.governance import filings as F
    top = org.entity("Gamma Group", kind="group", solo=False)
    sub = org.entity("Gamma Bank", parent=top)
    org.entity("Gamma Bank, Lisbon branch", parent=sub, kind="branch", solo=False)

    # a supervisor's date for the period, set for the organisation: kept while no filer is known
    s.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, source, set_by, filing_role)
                      VALUES (CAST(:o AS uuid), 'bank_tcfd', :pe, :pl, :due, 'supervisor', 'Test supervisor', 'whole_org')"""),
              {"o": org.id, "pe": org.pe, "pl": f"FY{org.pe.year}", "due": date(org.pe.year + 1, 4, 30)})
    assert org.owed() == {(None, "whole_org", "supervisor")}
    todo = F.filers_to_state(s, org.id, "bank")
    assert [(t["framework"], sorted(u["name"] for u in t["undertakings"])) for t in todo] == [
        ("bank_tcfd", ["Gamma Bank", "Gamma Group"])]                                     # not the branch
    assert todo[0]["undertakings"][0]["msg"]["code"] == "disclose.esrs.scope.role_needed"
    why = F.preflight(s, org.id, "bank", "bank_tcfd")
    assert why["needs_scope"] and why["scopes"] == [] and len(why["undetermined"]) == 2

    # the group stated to report for the group (Art. 29a), the bank exempt (Art. 19a(9)): the group is owed, carrying
    # the supervisor's date; the exempt subsidiary is not, and its scope is refused with its parent's report
    org.state_role(top, "consolidated")
    org.state_role(sub, "exempt_subsidiary", parent_name="Gamma Group", parent_registered_office="Frankfurt",
                   parent_report_ref="https://gamma.example/report")
    assert org.owed() == {(top, "consolidated", "supervisor")}
    assert F.filers_to_state(s, org.id, "bank") == []
    with pytest.raises(F.FilingError) as e:
        F.preflight(s, org.id, "bank", "bank_tcfd", entity_id=sub)
    assert e.value.code == "filing.refused.exempt_subsidiary_taxonomy" and e.value.params["parent"] == "Gamma Group"
    from services.governance.report_filers import record
    assert record(s, org.id, "bank_tcfd", top, True, org.pe)["level"] == "group"


def test_meridian_reports_through_its_filers_never_its_whole_book(api):
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    checker = _login(api, "approver@meridian.demo", "Demo!approve1")
    s = api.s
    from services.governance.filings import reporting_period_end
    from tests.integration.money_method import state_method
    pe = reporting_period_end(s, BANK_ORG)
    state_method(s, BANK_ORG, pe)
    grp = group(s, BANK_ORG)
    ents = dict(s.execute(text("SELECT name, entity_id::text FROM reporting_entities WHERE org_id = CAST(:o AS uuid)"),
                          {"o": BANK_ORG}).all())

    # 1 · the calendar owes Pillar 3 to the group; the Taxonomy report waits on the undertakings' roles
    cal = api.get("/v1/obligations", headers=maker).json()
    assert {(o["entity_id"], o["filing_role"]) for o in cal["obligations"]
            if o["framework"] == "bank_p3esg" and o["period_end"] == pe.isoformat() and o["entity_id"]} == {(grp, "consolidated")}
    todo = {t["framework"]: t for t in cal["filers_to_state"]}
    assert set(todo) == {"bank_tcfd"} and len(todo["bank_tcfd"]["undertakings"]) == 4

    # 2 · the whole organisation is refused with its filers; the pre-filing check offers them and says why
    pf = api.get("/v1/filings/preflight?framework=bank_p3esg", headers=maker).json()
    assert pf["needs_scope"] and pf["scopes"] == [{"entity_id": grp, "name": "Meridian Financial Group", "role": "consolidated"}]
    assert pf["scope_basis"]["title"] == "Who discloses ESG risks" and "Art. 13(1)" in pf["scope_basis"]["legal"]
    body = _refused(api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": "x"}),
                    "filing.refused.whole_org_no_filer")
    assert "Meridian Financial Group" in body["detail"]["next"] and "4 reporting entities" in body["detail"]["what"]
    tx = api.get("/v1/filings/preflight?framework=bank_tcfd", headers=maker).json()
    assert tx["needs_scope"] and tx["scopes"] == [] and len(tx["undetermined"]) == 4

    # 3 · the group's filing records its filer; its form says who reports and asks each subsidiary's size class
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg' "
                   "AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    pf = api.get(f"/v1/filings/preflight?framework=bank_p3esg&entity_id={grp}", headers=maker).json()
    g = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": pf["confirm_token"], "entity_id": grp})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    filer = s.execute(text("""SELECT s.payload -> '_filer' FROM regulatory_filing f JOIN report_snapshots s ON s.snapshot_id = f.snapshot_id
                              WHERE f.filing_id = CAST(:f AS uuid)"""), {"f": fid}).scalar()
    assert filer["level"] == "group" and filer["entity_id"] == grp
    assert {x["name"] for x in filer["subsidiaries"]} == {"Meridian Bank AG", "Meridian Corporate Finance", "Meridian Leasing GmbH"}
    secs = {x.get("key"): x for x in api.get(f"/v1/filings/{fid}/form", headers=maker).json()["annex"]["sections"]}
    assert secs["filer"]["rows"][0]["cells"][0]["text"] == "Meridian Financial Group"
    cell = next(r["cells"][1] for r in secs["large_institution"]["rows"] if r["cells"][0]["text"] == "Meridian Bank AG")

    # 4 · Meridian Bank AG stated a large institution through that cell (four eyes): the calendar owes its own report
    r = api.post("/v1/provided", headers=maker, json={"framework": cell["supply"]["framework"], "datapoint_key": cell["supply"]["key"],
                                                      "breakdown_member": cell["supply"]["member"], "value_text": "large",
                                                      "reporting_period_end": pe.isoformat()})
    assert r.status_code == 201, r.text
    assert api.post("/v1/provided", headers=maker, json={"framework": "bank_p3esg", "datapoint_key": "large_institution",
                                                         "breakdown_member": grp, "value_text": "large",
                                                         "reporting_period_end": pe.isoformat()}).status_code == 400   # not a subsidiary
    assert api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                    json={"decision": "approved"}).status_code == 200
    cal = api.get("/v1/obligations", headers=maker).json()["obligations"]
    assert {(o["entity_id"], o["filing_role"]) for o in cal if o["framework"] == "bank_p3esg" and o["period_end"] == pe.isoformat()
            and o["entity_id"]} == {(grp, "consolidated"), (ents["Meridian Bank AG"], "solo")}
    assert api.post(f"/v1/filings/{fid}/refresh", headers=maker).status_code == 200      # the draft freezes the statement
    secs = {x.get("key"): x for x in api.get(f"/v1/filings/{fid}/form", headers=maker).json()["annex"]["sections"]}
    row = next(r for r in secs["large_institution"]["rows"] if r["cells"][0]["text"] == "Meridian Bank AG")
    assert row["cells"][1]["frozen_value"] == "large" and row["cells"][2]["text"] == "approver@meridian.demo"

    # 5 · a whole-organisation filing frozen before exports no template; its JSON record stays readable
    old = s.execute(text("""SELECT filing_id::text FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_tcfd'
                            AND entity_id IS NULL AND status = 'accepted' LIMIT 1"""), {"o": BANK_ORG}).scalar()
    body = _refused(api.get(f"/v1/filings/{old}/export?format=xlsx", headers=maker), "filing.refused.whole_org_frozen")
    assert "EU Taxonomy Art. 8" in body["detail"]["what"]
    assert api.get(f"/v1/filings/{old}/export?format=json", headers=maker).status_code == 200

    # 6 · the group stated to report its Taxonomy KPIs for the group: the calendar owes it
    state_role(api, maker, checker, grp, pe)
    cal = api.get("/v1/obligations", headers=maker).json()
    assert (grp, "consolidated") in {(o["entity_id"], o["filing_role"]) for o in cal["obligations"]
                                     if o["framework"] == "bank_tcfd" and o["period_end"] == pe.isoformat()}
    assert len({t["framework"]: t for t in cal["filers_to_state"]}["bank_tcfd"]["undertakings"]) == 3


def test_an_exempt_subsidiary_reports_no_taxonomy_kpis_of_its_own(api):
    maker = _login(api, "admin@stellar.demo", "Demo!admin1")
    checker = _login(api, "approver@stellar.demo", "Demo!approve1")
    s = api.s
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, STELLAR)
    fund = s.execute(text("SELECT entity_id::text FROM reporting_entities WHERE org_id = CAST(:o AS uuid) AND name = 'Stellar Logistics Fund I'"),
                     {"o": STELLAR}).scalar_one()
    _refused(api.post("/v1/filings", headers=maker, json={"framework": "reit_taxonomy", "confirm_token": "x"}),
             "filing.refused.whole_org_no_filer")
    state_role(api, maker, checker, fund, pe, role="exempt_subsidiary", parent_name="Stellar Group",
               parent_registered_office="Amsterdam", parent_report_ref="https://stellar.example/annual-report")
    body = _refused(api.get(f"/v1/filings/preflight?framework=reit_taxonomy&entity_id={fund}", headers=maker),
                    "filing.refused.exempt_subsidiary_taxonomy")
    assert "Stellar Group" in body["detail"]["what"] and "C/2023/305" in body["detail"]["why"]


def test_iberia_reports_its_orsa_through_an_undertaking_or_the_group(api):
    """The ORSA's filers are Solvency II's (Delegated Regulation (EU) 2015/35 Arts 304(1)(c), 372(1); E350): Iberia's
    documents page offers its group and undertakings only, the whole organisation is refused for the document and its
    filing, and the group's filing would record the group's report. The recovery plan keeps the organisation until the
    IRRD's text is held."""
    from tests.integration.test_e2e_s2701 import GROUP, IBERIA, IBERIA_RE, SEGUROS, _users
    maker, _, _ = _users(api)
    who = api.get("/v1/filings/filers?framework=insurer_orsa_climate", headers=maker).json()
    assert not who["organisation"] and [(f["entity_id"], f["role"]) for f in who["filers"]] == [
        (GROUP, "consolidated"), (SEGUROS, "solo"), (IBERIA_RE, "solo")]
    assert who["scope_basis"]["title"] == "Who reports the ORSA" and "Art. 372(1)" in who["scope_basis"]["legal"]
    body = _refused(api.get("/v1/insurance/documents/insurer_orsa_climate", headers=maker), "filing.refused.whole_org_no_filer")
    assert "Iberia Mutual Group" in body["detail"]["next"]
    _refused(api.put("/v1/insurance/documents/insurer_orsa_climate/answers", headers=maker, json={"answers": {}}),
             "filing.refused.whole_org_no_filer")
    pf = api.get("/v1/filings/preflight?framework=insurer_orsa_climate", headers=maker).json()
    assert pf["needs_scope"] and [s["entity_id"] for s in pf["scopes"]] == [GROUP, SEGUROS, IBERIA_RE]
    assert api.get(f"/v1/insurance/documents/insurer_orsa_climate?entity_id={GROUP}", headers=maker).status_code == 200
    from services.governance.filings import reporting_period_end
    from services.governance.report_filers import record
    pe = reporting_period_end(api.s, IBERIA)
    assert record(api.s, IBERIA, "insurer_orsa_climate", GROUP, True, pe)["basis"].startswith(
        "Delegated Regulation (EU) 2015/35 Art. 372(1)")
    assert record(api.s, IBERIA, "insurer_orsa_climate", SEGUROS, False, pe)["level"] == "undertaking"
    assert api.get("/v1/filings/filers?framework=insurer_recovery_stress", headers=maker).json()["organisation"] is True
    assert api.get("/v1/filings/filers?framework=no_such_report", headers=maker).status_code == 404
