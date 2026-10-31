"""An insurance undertaking at the head of a group owes its own ORSA beside the group's (E353), end to end.

  Directive 2009/138/EC Art. 45(1) binds "every insurance undertaking" to its own risk and solvency assessment; Art. 246(4)
  binds the participating undertaking to the group's. Iberia, restructured in the test so Iberia Mutual Seguros heads the
  group (Iberia Re, 60 % proportional, below it), as E348's test does:
  calendar  Seguros owes two ORSAs — its own and the group's — and Iberia Re its own, each with no date of its own until
            its filing gives the conclusion (Del. Reg. 2015/35 Art. 312(1)(b)); then both due the same day (Art. 373:
            the ORSA is not extended for a group)
  figures   the live document of each reads its own book (Seguros alone, or the group's consolidated book) and its own
            attested capital — never the other's
  answers   each report keeps its own answers
  filings   both live at once, each the answer to its own obligation and recorded as its own filer's report (Art. 304(1)(c)
            for the undertaking, Art. 372(1) for the group); a second own ORSA refused while one is live
  refusals  a group's ORSA for an entity with nothing below it; a parent's own recovery plan (one scope per entity)
  database  a date-less obligation is the ORSA's only

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.money_method import state_method
from tests.integration.test_e2e_s2701 import IBERIA, IBERIA_RE, SEGUROS, _users
from tests.integration.test_e2e_sii_parent_own import _refused, _state

pytestmark = pytest.mark.integration
FW = "insurer_orsa_climate"


def _payload(api, maker, fid: str) -> dict:
    return json.loads(api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).content)["payload"]


def test_an_undertaking_at_the_head_of_a_group_owes_its_own_orsa_and_the_group_s(api):
    maker, checker, _ = _users(api)
    s = api.s
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, IBERIA)
    state_method(s, IBERIA, pe)
    # Seguros heads the group: Iberia Re (60 %, proportional) below it; the group node above nothing any more
    s.execute(text("UPDATE reporting_entities SET parent_entity_id = NULL WHERE entity_id = CAST(:e AS uuid)"), {"e": SEGUROS})
    s.execute(text("UPDATE reporting_entities SET parent_entity_id = CAST(:p AS uuid) WHERE entity_id = CAST(:e AS uuid)"),
              {"e": IBERIA_RE, "p": SEGUROS})
    si = dict(s.execute(text("""SELECT reporting_entity_id::text, sum(primary_value_eur)::float FROM portfolio_entities
                                WHERE org_id = CAST(:o AS uuid) AND vertical = 'insurance' AND source = 'own' GROUP BY 1"""),
                        {"o": IBERIA}).all())

    # 1 · the calendar owes Seguros two ORSAs and Iberia Re its own, none dated before its conclusion is known
    def owed() -> dict:
        cal = api.get("/v1/obligations", headers=maker).json()["obligations"]
        return {(o["entity_id"], o["filing_role"]): o for o in cal if o["framework"] == FW and o["period_end"] == pe.isoformat()}
    ob = owed()
    assert set(ob) == {(SEGUROS, "consolidated"), (SEGUROS, "solo"), (IBERIA_RE, "solo")}
    assert all(o["due_date"] is None and o["days_to_due"] is None and not o["overdue"] for o in ob.values())
    assert all("2 weeks after concluding the assessment" in o["due_rule"] for o in ob.values())
    assert all(o["scope_role"] == role for (_, role), o in ob.items())          # the role the prepare dialog sends
    who = api.get(f"/v1/filings/filers?framework={FW}", headers=maker).json()
    assert [(f["entity_id"], f["role"]) for f in who["filers"]] == [(SEGUROS, "consolidated"), (SEGUROS, "solo"), (IBERIA_RE, "solo")]
    assert "head of a group reports both" in who["scope_basis"]["shows"]

    # 2 · each ORSA's figures: its own book and its own attested capital
    _state(api, maker, checker, pe, {"eligible_own_funds_scr": 150_000_000, "scr_total": 100_000_000}, SEGUROS, "solo")
    _state(api, maker, checker, pe, {"eligible_own_funds_scr": 420_000_000, "scr_total": 300_000_000}, SEGUROS, "consolidated")

    def doc(role: str | None, entity: str = SEGUROS, fw: str = FW):
        return api.get(f"/v1/insurance/documents/{fw}?entity_id={entity}" + (f"&filing_role={role}" if role else ""),
                       headers=maker)
    own, grp, plain = doc("solo").json(), doc("consolidated").json(), doc(None).json()
    assert (own["filing_role"], grp["filing_role"], plain["filing_role"]) == ("solo", "consolidated", "consolidated")
    assert own["computed"]["capital"]["scr_total"] == 100_000_000 and grp["computed"]["capital"]["scr_total"] == 300_000_000
    assert own["computed"]["today"]["sum_insured_eur"] == pytest.approx(si[SEGUROS], rel=1e-6)          # no Iberia Re in it
    assert grp["computed"]["today"]["sum_insured_eur"] == pytest.approx(si[SEGUROS] + 0.6 * si[IBERIA_RE], rel=1e-6)

    # 3 · each ORSA's answers are its own
    def put(role: str, text_: str):
        r = api.put(f"/v1/insurance/documents/{FW}/answers", headers=maker,
                    json={"answers": {"sfcr.actions": {"text": text_}}, "entity_id": SEGUROS, "filing_role": role})
        assert r.status_code == 200 and not r.json()["refused"], r.text
    put("solo", "Seguros: wildfire accumulation limits in Valencia.")
    put("consolidated", "Group: one catastrophe programme across Iberia.")
    answer = lambda d: {i["id"]: i for i in d["items"]}["sfcr.actions"]["value"]["text"]   # noqa: E731
    assert answer(doc("solo").json()).startswith("Seguros") and answer(doc("consolidated").json()).startswith("Group")

    # 4 · refusals: a group's ORSA for an entity with nothing below it; a parent's own recovery plan
    _refused(doc("consolidated", IBERIA_RE), "filing.refused.role_scope")
    _refused(doc("solo", SEGUROS, "insurer_recovery_stress"), "filing.refused.own_book_not_offered")

    # 5 · both filed for their obligations, concluded on 31 March 2027: each its filer's report, both due 14 April
    def prepare(role: str) -> dict:
        pf = api.get(f"/v1/filings/preflight?framework={FW}&entity_id={SEGUROS}&filing_role={role}", headers=maker).json()
        assert pf["filing_role"] == role
        g = api.post("/v1/filings", headers=maker, json={"framework": FW, "confirm_token": pf["confirm_token"],
                                                         "obligation_id": ob[(SEGUROS, role)]["obligation_id"],
                                                         "disclosure_date": "2027-03-31"})
        assert g.status_code == 201, g.text
        return g.json()
    mine, group = prepare("solo"), prepare("consolidated")
    assert (mine["filing_role"], group["filing_role"]) == ("solo", "consolidated")
    p, q = _payload(api, maker, mine["filing_id"]), _payload(api, maker, group["filing_id"])
    assert p["_scope"] == {"reporting_entity_id": SEGUROS, "filing_role": "solo"}
    assert q["_scope"] == {"reporting_entity_id": SEGUROS, "filing_role": "consolidated"}
    assert p["_filer"]["level"] == "undertaking" and "Art. 304(1)(c)" in p["_filer"]["basis"]
    assert q["_filer"]["level"] == "group" and "Art. 372(1)" in q["_filer"]["basis"]
    assert p["document_report"]["answers"]["sfcr.actions"]["text"].startswith("Seguros")
    assert q["document_report"]["answers"]["sfcr.actions"]["text"].startswith("Group")
    assert p["document_report"]["computed"]["capital"]["scr_total"] == 100_000_000
    assert q["document_report"]["computed"]["capital"]["scr_total"] == 300_000_000
    due = {api.get(f"/v1/filings/{f['filing_id']}", headers=maker).json()["due_date"] for f in (mine, group)}
    assert due == {"2027-04-14"}                                    # Art. 312(1)(b); Art. 373: no six weeks for the group

    # 6 · the calendar: each obligation answered by its own filing and dated from its conclusion
    ob = owed()
    assert ob[(SEGUROS, "solo")]["filing_id"] == mine["filing_id"] and ob[(SEGUROS, "consolidated")]["filing_id"] == group["filing_id"]
    assert ob[(SEGUROS, "solo")]["due_date"] == ob[(SEGUROS, "consolidated")]["due_date"] == "2027-04-14"
    assert ob[(IBERIA_RE, "solo")]["filing_id"] is None and ob[(IBERIA_RE, "solo")]["due_date"] is None
    again = api.get(f"/v1/filings/preflight?framework={FW}&entity_id={SEGUROS}&filing_role=solo", headers=maker).json()
    assert not again["can_generate"] and again["existing_status"] == "draft"

    # 7 · the database: an obligation without a date is the ORSA's only
    sp = s.begin_nested()
    with pytest.raises(IntegrityError):
        s.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency,
                                                             entity_id, filing_role)
                          VALUES (CAST(:o AS uuid), 'insurer_solvency', :pe, :pl, NULL, 'annual', CAST(:e AS uuid), 'solo')"""),
                  {"o": IBERIA, "pe": pe, "pl": f"FY{pe.year}", "e": IBERIA_RE})
    sp.rollback()
