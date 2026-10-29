"""Who reports Solvency II natural catastrophe risk (services.governance.sii_filers), end to end.

  ITS (EU) 2023/894 has two filers of S.27.01: an undertaking for itself (S.27.01.01, Art. 19(1)(s)(i), its own LEI —
  Annex II S.01.02 C0010/R0020) and a group (S.27.01.04, Art. 34(1)(s), by the participating undertaking at its head —
  Annex III S.01.02 C0010/R0010, R0020). An organisation that records its undertakings is, as a whole, neither:
  calendar  with no reporting entity the organisation owes its own report; with one undertaking, that undertaking's one
            report (E348: never a whole-organisation copy beside it); with more, one per group (a top entity with an
            undertaking below it, due 6 weeks later — Del. Reg. Art. 373) and per undertaking, none for the whole
            organisation; a supervisor's whole-organisation date moves onto every filer's obligation for its period
            (later filers too); a top that is itself an undertaking set to file owes both its own report and the
            group's (E348), a node of kind 'group' only the group's; a branch heads no group and is in its own book
  publish   a supervisor's deadline published for Iberia lands on the group's and each undertaking's obligation
  scope     Iberia (three entities): the pre-filing check offers the group and the undertakings; generate refuses the
            whole organisation with the reason; a whole-organisation draft frozen without a filer record cannot be
            refreshed
  exports   that draft exports no template (XBRL and workbook refused with the reason; its JSON record readable; its form
            says why); the undertaking's and the group's filings record their filer

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.integration.money_method import state_method
from tests.integration.test_e2e_s2701 import GROUP, IBERIA, IBERIA_RE, SEGUROS, _generate, _users

pytestmark = pytest.mark.integration
FW = "insurer_solvency"
INS_SUP = "88888888-8888-4888-8888-888888888802"          # EU Insurance Supervisor (demo) — Iberia is in its scope


def _refused(resp, code: str) -> dict:
    assert resp.status_code == 409, resp.text
    body = resp.json()["error"]
    assert body["error"] == code, resp.text
    return body


def test_the_calendar_owes_the_filers_reports_and_never_the_whole_organisation_of_several(session_rolled_back):
    s = session_rolled_back
    from services.governance import filings as F
    org = str(uuid.uuid4())
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (CAST(:o AS uuid), :n, 'insurer', 'ES')"),
              {"o": org, "n": f"Filers test {org[:8]}"})
    pe = F.reporting_period_end(s, org)
    undertaking_due = F._due_date(FW, pe)

    def owed_now() -> set:
        F.ensure_obligations(s, org, "insurer")
        return {(r[0], r[1]) for r in s.execute(text("""
            SELECT entity_id::text, filing_role FROM regulatory_obligation
            WHERE org_id = CAST(:o AS uuid) AND framework = :f AND period_end = :pe"""), {"o": org, "f": FW, "pe": pe}).all()}

    def due_of(eid: str, role: str) -> date:
        return s.execute(text("""SELECT due_date FROM regulatory_obligation WHERE org_id = CAST(:o AS uuid) AND framework = :f
                                 AND period_end = :pe AND entity_id = CAST(:e AS uuid) AND filing_role = :r"""),
                         {"o": org, "f": FW, "pe": pe, "e": eid, "r": role}).scalar()

    def entity(name: str, parent: str | None = None, solo: bool = True, pct: float = 100, method: str = "full",
               kind: str = "legal_entity") -> str:
        eid = str(uuid.uuid4())
        s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name, kind, parent_entity_id, ownership_pct,
                                                          consolidation_method, requires_solo_filing)
                          VALUES (CAST(:e AS uuid), CAST(:o AS uuid), :n, :k, CAST(:p AS uuid), :pct, :m, :solo)"""),
                  {"e": eid, "o": org, "n": name, "k": kind, "p": parent, "pct": pct, "m": method, "solo": solo})
        return eid

    # no reporting entity: the organisation is the undertaking
    assert owed_now() == {(None, "whole_org")}
    # a supervisor's own deadline for the period before, set for the organisation (it is the undertaking): it stays
    prev, sup_due = date(pe.year - 1, 12, 31), date(pe.year, 4, 7)
    s.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, source, set_by, filing_role)
                      VALUES (CAST(:o AS uuid), :f, :pe, :pl, :due, 'supervisor', 'Test supervisor', 'whole_org')"""),
              {"o": org, "f": FW, "pe": prev, "pl": f"FY{prev.year}", "due": sup_due})

    def supervisor_dated() -> set:
        return {(r[0], r[1], r[2], r[3]) for r in s.execute(text("""
            SELECT entity_id::text, source, set_by, due_date FROM regulatory_obligation
            WHERE org_id = CAST(:o AS uuid) AND framework = :f AND period_end = :pe"""), {"o": org, "f": FW, "pe": prev}).all()}
    assert owed_now() == {(None, "whole_org")}
    assert supervisor_dated() == {(None, "supervisor", "Test supervisor", sup_due)}

    # one undertaking recorded: it reports for itself, once — the whole organisation is no second filer of its S.27.01.01
    alpha = entity("Alpha Seguros")
    assert owed_now() == {(alpha, "solo")}
    assert supervisor_dated() == {(alpha, "supervisor", "Test supervisor", sup_due)}     # the supervisor's date moved onto it

    # a second undertaking side by side: each owes its own report, the whole organisation none
    beta = entity("Beta Re", solo=True)
    assert owed_now() == {(alpha, "solo"), (beta, "solo")}
    assert supervisor_dated() == {(alpha, "supervisor", "Test supervisor", sup_due), (beta, "supervisor", "Test supervisor", sup_due)}

    # a holding above both (Beta proportional at 60 %): the group owes S.27.01.04, each undertaking its S.27.01.01; the
    # group's report is due 6 weeks after the undertakings' (Del. Reg. 2015/35 Art. 373)
    top = entity("Alpha Group", solo=False)
    s.execute(text("UPDATE reporting_entities SET parent_entity_id = CAST(:t AS uuid) WHERE entity_id IN (CAST(:a AS uuid), CAST(:b AS uuid))"),
              {"t": top, "a": alpha, "b": beta})
    s.execute(text("UPDATE reporting_entities SET ownership_pct = 60, consolidation_method = 'proportional' WHERE entity_id = CAST(:b AS uuid)"),
              {"b": beta})
    assert owed_now() == {(top, "consolidated"), (alpha, "solo"), (beta, "solo")}
    assert supervisor_dated() == {(e, "supervisor", "Test supervisor", sup_due) for e in (top, alpha, beta)}   # the group too
    assert due_of(alpha, "solo") == undertaking_due and due_of(top, "consolidated") == undertaking_due + timedelta(weeks=6)

    # the top is itself an insurance undertaking set to file its own report: it owes both — the group's and its own
    s.execute(text("UPDATE reporting_entities SET requires_solo_filing = true WHERE entity_id = CAST(:t AS uuid)"), {"t": top})
    assert owed_now() == {(top, "consolidated"), (top, "solo"), (alpha, "solo"), (beta, "solo")}
    assert due_of(top, "solo") == undertaking_due and due_of(top, "consolidated") == undertaking_due + timedelta(weeks=6)
    # ... and a calendar row whose role is owed no more is the entity's report under the role it is owed now
    s.execute(text("UPDATE reporting_entities SET requires_solo_filing = false WHERE entity_id = CAST(:t AS uuid)"), {"t": top})
    assert owed_now() == {(top, "consolidated"), (alpha, "solo"), (beta, "solo")}

    # a node that stands for the group (kind 'group') is no undertaking: set to file, it still owes only the group's report
    s.execute(text("UPDATE reporting_entities SET kind = 'group', requires_solo_filing = true WHERE entity_id = CAST(:t AS uuid)"),
              {"t": top})
    assert owed_now() == {(top, "consolidated"), (alpha, "solo"), (beta, "solo")}

    # a branch is part of its undertaking: an undertaking with only a branch below it heads no group, and its own book
    # holds the branch (ITS 2023/894 Annex II S.04.03: a contract "sold through a branch" is the undertaking's business)
    org2 = str(uuid.uuid4())
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (CAST(:o AS uuid), :n, 'insurer', 'ES')"),
              {"o": org2, "n": f"Branch test {org2[:8]}"})
    org, keep = org2, org
    head = entity("Gamma Seguros")
    branch = entity("Gamma Seguros, Lisbon branch", parent=head, solo=False, kind="branch")
    assert owed_now() == {(head, "solo")}
    from services.governance.entities import own_book_ids, subtree_ids
    assert set(own_book_ids(s, org, head)) == {head, branch} == set(subtree_ids(s, org, head))
    sub = entity("Gamma Vida", parent=branch)                    # an undertaking below the branch: a group now
    assert owed_now() == {(head, "consolidated"), (head, "solo"), (sub, "solo")}
    assert set(own_book_ids(s, org, head)) == {head, branch}     # its own book never takes the undertaking below
    org = keep


def test_iberia_reports_through_its_group_and_undertakings_never_its_whole_book(api):
    maker, checker, admin = _users(api)
    s = api.s
    from services.governance.filings import reporting_period_end
    from services.governance.report_snapshots import create_snapshot
    pe = reporting_period_end(s, IBERIA)
    state_method(s, IBERIA, pe)

    # 1 · the calendar owes the group's report and each undertaking's, no whole-organisation one
    cal = api.get("/v1/obligations", headers=maker).json()["obligations"]
    assert {(o["entity_id"], o["filing_role"]) for o in cal if o["framework"] == FW and o["period_end"] == pe.isoformat()} == {
        (GROUP, "consolidated"), (SEGUROS, "solo"), (IBERIA_RE, "solo")}

    # 1b · a supervisor publishes its date for an earlier year: it lands on the filers' obligations, not the whole organisation
    from services.supervision import deadlines
    fy = pe.year - 2
    sup_user = s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@insurance-supervisor.demo'")).scalar()
    did = str(s.execute(text("""
        INSERT INTO supervision_deadline (regulator_org_id, mandate_id, framework, period_label, period_end, due_date, due_source)
        VALUES (CAST(:r AS uuid), 'solvency2_qrt_natcat', :f, :pl, :pe, :due, 'set') RETURNING deadline_id"""),
        {"r": INS_SUP, "f": FW, "pl": f"FY{fy}", "pe": date(fy, 12, 31), "due": date(fy + 1, 4, 1)}).scalar())
    assert deadlines.publish(s, INS_SUP, did, sup_user, None)["entities_set"] >= 1
    dated = s.execute(text("""SELECT entity_id::text, filing_role, source, due_date FROM regulatory_obligation
                              WHERE org_id = CAST(:o AS uuid) AND framework = :f AND period_end = :pe"""),
                      {"o": IBERIA, "f": FW, "pe": date(fy, 12, 31)}).all()
    assert {tuple(r) for r in dated} == {(e, role, "supervisor", date(fy + 1, 4, 1)) for e, role in
                                         ((GROUP, "consolidated"), (SEGUROS, "solo"), (IBERIA_RE, "solo"))}

    # 2 · the pre-filing check offers the filers; generate refuses the whole organisation with the reason
    pf = api.get(f"/v1/filings/preflight?framework={FW}", headers=maker)
    assert pf.status_code == 200, pf.text
    pf = pf.json()
    assert pf["needs_scope"] and not pf["can_generate"] and pf["confirm_token"] is None
    assert pf["scopes"] == [{"entity_id": GROUP, "name": "Iberia Mutual Group", "role": "consolidated"},
                            {"entity_id": SEGUROS, "name": "Iberia Mutual Seguros", "role": "solo"},
                            {"entity_id": IBERIA_RE, "name": "Iberia Re", "role": "solo"}]
    body = _refused(api.post("/v1/filings", headers=maker, json={"framework": FW, "confirm_token": "x"}), "filing.refused.sii_whole_org")
    assert "Iberia Mutual Group (group), Iberia Mutual Seguros, Iberia Re" in str(body)

    # 3 · a whole-organisation draft frozen without a filer record (as an earlier release froze one)
    for (live,) in s.execute(text("""SELECT filing_id::text FROM regulatory_filing WHERE org_id = CAST(:o AS uuid) AND framework = :f
                                     AND period_end = :pe AND entity_id IS NULL AND status NOT IN ('superseded', 'withdrawn')"""),
                             {"o": IBERIA, "f": FW, "pe": pe}).all():
        assert api.post(f"/v1/filings/{live}/withdraw", headers=maker, json={"reason": "replaced by the test's draft"}).status_code == 200
    user = s.execute(text("SELECT user_id::text FROM users WHERE email = 'analyst@iberia.demo'")).scalar()
    snap = create_snapshot(s, IBERIA, FW, user, period_end=pe)
    assert s.execute(text("SELECT payload ? '_filer' FROM report_snapshots WHERE snapshot_id = CAST(:i AS uuid)"),
                     {"i": snap["snapshot_id"]}).scalar() is False   # the whole book of three entities is no filer's
    fid = str(s.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, created_by, filing_role)
        VALUES (CAST(:o AS uuid), :f, :pe, :pl, 'draft', CAST(:snap AS uuid), CAST(:u AS uuid), 'whole_org') RETURNING filing_id"""),
        {"o": IBERIA, "f": FW, "pe": pe, "pl": f"FY{pe.year}", "snap": snap["snapshot_id"], "u": user}).scalar())
    _refused(api.post(f"/v1/filings/{fid}/refresh", headers=maker), "filing.refused.sii_whole_org")
    for fmt in ("xbrl", "xlsx"):
        _refused(api.get(f"/v1/filings/{fid}/export?format={fmt}", headers=maker), "filing.refused.sii_whole_org_frozen")
    assert api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).status_code == 200      # the record stays readable
    summary = next(x for x in api.get(f"/v1/filings/{fid}/form", headers=maker).json()["annex"]["sections"] if x.get("key") == "s2701_summary")
    assert summary["note"].startswith("Not exported: frozen for the whole organisation")

    # 4 · the undertaking's and the group's reports record their filer and produce their templates
    fid, payload = _generate(api, maker, FW, SEGUROS)
    assert payload["_filer"] == {"level": "undertaking", "entity_id": SEGUROS, "template": "S.27.01.01",
                                 "basis": "Implementing Regulation (EU) 2023/894 Art. 19(1)(s)(i)"}
    assert api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker).status_code == 200
    fid, payload = _generate(api, maker, FW, GROUP)
    assert payload["_filer"] == {"level": "group", "entity_id": GROUP, "template": "S.27.01.04",
                                 "basis": "Implementing Regulation (EU) 2023/894 Art. 34(1)(s)"}
    assert api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker).status_code == 200
