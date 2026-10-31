"""Pillar 3 ESG twice a year for a G-SII or a listed large institution (E354), end to end.

  periods     the database derives a label from a period's end and kind as services.governance.periods does
              (FY2026, FY2026-H1), refuses a half-year for a report disclosed only for a financial year, and an
              obligation for a half-year that is not semi-annual
  calendar    an organisation that records no entity is the institution: once it states itself a G-SII, the half-year
              of its financial year is owed (due three months after it); a financial-year period owes the year end and
              its first half
  Meridian    (a group over three subsidiaries) through the API, with the period set to a half-year nothing is stated
              for yet (the first half of FY2026 unless the demo data states one — tests.integration.filers): the
              cockpit asks for the size class and listing of each possible filer; nothing is owed and the group's
              half-year report is refused until they are stated; the EU Taxonomy report is refused for a half-year; the
              group stated a listed large institution (four eyes) is owed its half-year report, due 30 September; a
              subsidiary stated large and not listed discloses once a year and is refused; the group's half-year filing
              is labelled FY2026-H1, freezes its period and its filer's frequency, prints its disclosure period, and
              downloads as the EBA's data hub package for 30 June 2026; the year end then owes the year's report beside it

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import re
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from services.governance import periods as P
from services.governance.reporting_settings import upsert_reporting_settings
from tests.integration.conftest import login as _login
from tests.integration.filers import group, half_year_without_statements
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
H1 = date(2026, 6, 30)


def _org(s) -> str:
    oid = str(uuid.uuid4())
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (CAST(:o AS uuid), :n, 'bank', 'DE')"),
              {"o": oid, "n": f"Semi-annual test {oid[:8]}"})
    return oid


def _obligation(s, org: str, framework: str, end: date, kind: str, label: str, frequency: str = "semiannual"):
    with s.begin_nested():
        s.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_kind, period_label,
                                                             due_date, frequency, filing_role)
                          VALUES (CAST(:o AS uuid), :f, :e, :k, :l, :d, :q, 'whole_org')"""),
                  {"o": org, "f": framework, "e": end, "k": kind, "l": label, "d": date(2027, 1, 1), "q": frequency})


def test_the_database_derives_a_periods_label_as_the_platform_does(session_rolled_back):
    s = session_rolled_back
    org = _org(s)
    for end, kind in ((date(2026, 6, 30), "half_year"), (date(2025, 12, 31), "half_year"), (date(2026, 2, 28), "half_year"),
                      (date(2026, 12, 31), "financial_year"), (date(2026, 3, 31), "financial_year")):
        _obligation(s, org, "bank_p3esg", end, kind, P.label(end, kind),
                    "semiannual" if kind == "half_year" else "annual")
    for bad in (("bank_p3esg", H1, "half_year", "FY2026", "semiannual"),        # a half-year labelled as its year
                ("bank_tcfd", H1, "half_year", "FY2026-H1", "semiannual"),       # a half-year of an annual report
                ("bank_p3esg", H1, "half_year", "FY2026-H1", "annual")):         # a half-year owed once a year
        with pytest.raises(IntegrityError):
            _obligation(s, org, *bad)


def _state(s, org: str, key: str, value: str, member: str, period_end: date) -> None:
    from services.governance import provided_data as Pd
    maker, checker = s.execute(text("""SELECT user_id::text FROM users WHERE email IN
        ('admin@meridian.demo', 'approver@meridian.demo') ORDER BY email""")).scalars().all()
    r = Pd.submit(s, org, maker, framework="bank_p3esg", datapoint_key=key, value_text=value, breakdown_member=member,
                  reporting_period_end=period_end.isoformat())
    Pd.attest(s, org, {"provided_id": r["provided_id"]}, "approved", checker)


def _owed(s, org: str) -> set:
    from services.governance import filings as F
    F.ensure_obligations(s, org, "bank")
    return {(r[0], r[1], r[2], r[3], r[4]) for r in s.execute(text("""
        SELECT period_end, period_kind, period_label, frequency, due_date FROM regulatory_obligation
        WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg'"""), {"o": org}).all()}


def test_an_institution_on_its_own_owes_the_half_year_once_it_states_itself_a_gsii(session_rolled_back):
    s = session_rolled_back
    org = _org(s)
    upsert_reporting_settings(s, org, {"reporting_period_end": "2026-12-31"}, None)
    year = (date(2026, 12, 31), "financial_year", "FY2026", "annual", date(2027, 4, 30))
    assert _owed(s, org) == {year}                                       # the year end only, while nothing is stated
    from services.governance import filings as F
    todo = {t["period_label"]: t for t in F.filers_to_state(s, org, "bank") if t["framework"] == "bank_p3esg"}
    me = todo["FY2026-H1"]["undertakings"][0]
    assert me["entity_id"] is None and me["member"] == org and me["needs"] == ["size", "listing"]
    _state(s, org, "large_institution", "gsii", org, H1)                 # the organisation states its own, keyed by itself
    assert _owed(s, org) == {year, (H1, "half_year", "FY2026-H1", "semiannual", date(2026, 9, 30))}
    # a half-year period owes only the half-year
    upsert_reporting_settings(s, org, {"reporting_period_end": "2027-06-30", "reporting_period_kind": "half_year"}, None)
    _state(s, org, "large_institution", "not_large", org, date(2027, 6, 30))
    assert {r[0] for r in _owed(s, org)} == {date(2026, 12, 31), H1}    # not large at 30 June 2027: nothing new


def _post_state(api, maker, checker, key: str, value: str, member: str, period_end: date) -> None:
    r = api.post("/v1/provided", headers=maker, json={"framework": "bank_p3esg", "datapoint_key": key, "value_text": value,
                                                      "breakdown_member": member, "reporting_period_end": period_end.isoformat()})
    assert r.status_code == 201, r.text
    d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker, json={"decision": "approved"})
    assert d.status_code == 200, d.text


def _lei(base18: str) -> str:
    n = int("".join(str(int(c, 36)) for c in base18 + "00"))
    return f"{base18}{98 - n % 97:02d}"


def test_meridian_discloses_its_half_year_through_its_listed_group(api, tmp_path):
    from scripts.validate_p3esg_xbrlcsv import filing_rules
    from tests.integration.money_method import state_method
    maker = _login(api, "admin@meridian.demo", "Demo!admin1")
    checker = _login(api, "approver@meridian.demo", "Demo!approve1")
    s = api.s
    # a half-year with nothing stated for it yet, as the organisation's period (the first half of FY2026 unless stated)
    h = half_year_without_statements(s, BANK_ORG)
    fy, hl = P.financial_year_end(h, P.HALF_YEAR), P.label(h, P.HALF_YEAR)
    fyl, due = P.label(P.financial_year_end(h, P.HALF_YEAR)), P.add_months(h, 3).isoformat()
    state_method(s, BANK_ORG, h)
    s.execute(text("UPDATE regulatory_filing SET status = 'superseded' WHERE org_id = CAST(:o AS uuid) AND framework = 'bank_p3esg' "
                   "AND status NOT IN ('superseded', 'withdrawn')"), {"o": BANK_ORG})
    grp = group(s, BANK_ORG)
    ents = dict(s.execute(text("SELECT name, entity_id::text FROM reporting_entities WHERE org_id = CAST(:o AS uuid)"),
                          {"o": BANK_ORG}).all())
    basis = api.get("/v1/filings/reporting-basis", headers=maker).json()
    assert basis["reporting_period_label"] == hl and {k["value"] for k in basis["period_kinds"]} == set(P.KINDS)

    # 1 · nothing is owed for the half-year yet: the cockpit asks for each possible filer's size class and listing
    cal = api.get("/v1/obligations", headers=maker).json()
    assert not [o for o in cal["obligations"] if o["period_kind"] == "half_year"]
    todo = [t for t in cal["filers_to_state"] if t["framework"] == "bank_p3esg"]
    assert [t["period_label"] for t in todo] == [hl]
    asked = {u["name"]: u for u in todo[0]["undertakings"]}
    assert set(asked) == {"Meridian Financial Group", "Meridian Bank AG", "Meridian Corporate Finance", "Meridian Leasing GmbH"}
    assert [x["key"] for x in asked["Meridian Financial Group"]["statements"]] == ["large_institution", "listed_institution"]
    assert asked["Meridian Bank AG"]["msg"]["code"] == "filing.to_state.esg_half_year"

    # 2 · the group's half-year report is refused while unstated; the EU Taxonomy report is never one for a half-year
    r = api.get(f"/v1/filings/preflight?framework=bank_p3esg&entity_id={grp}", headers=maker)
    assert r.status_code == 409 and r.json()["error"]["error"] == "filing.refused.esg_frequency_unstated", r.text
    r = api.get("/v1/filings/preflight?framework=bank_tcfd", headers=maker)
    assert r.status_code == 409 and r.json()["error"]["error"] == "filing.refused.annual_period_only", r.text
    assert hl in r.json()["error"]["detail"]["what"]

    # 3 · the group a listed large institution (four eyes): owed its half-year report, due three months after it; a
    # subsidiary large and not listed discloses once a year — not owed, and refused
    _post_state(api, maker, checker, "large_institution", "large", grp, h)
    _post_state(api, maker, checker, "listed_institution", "listed", grp, h)
    _post_state(api, maker, checker, "large_institution", "large", ents["Meridian Bank AG"], h)
    _post_state(api, maker, checker, "listed_institution", "non_listed", ents["Meridian Bank AG"], h)
    cal = api.get("/v1/obligations", headers=maker).json()
    half = [o for o in cal["obligations"] if o["period_kind"] == "half_year"]
    assert [(o["entity_id"], o["filing_role"], o["period_label"], o["due_date"], o["frequency"]) for o in half] == [
        (grp, "consolidated", hl, due, "semiannual")]
    r = api.get(f"/v1/filings/preflight?framework=bank_p3esg&entity_id={ents['Meridian Bank AG']}", headers=maker)
    assert r.status_code == 409 and r.json()["error"]["error"] == "filing.refused.esg_annual_filer", r.text
    assert "433a(2)" in r.json()["error"]["detail"]["why"]                 # the citation in the pop-up only
    pf = api.get("/v1/filings/preflight?framework=bank_p3esg", headers=maker).json()     # the whole organisation: its filers
    assert pf["needs_scope"] and [c["entity_id"] for c in pf["scopes"]] == [grp]

    # 4 · the group's half-year filing for its obligation
    pf = api.get(f"/v1/filings/preflight?framework=bank_p3esg&entity_id={grp}", headers=maker).json()
    assert pf["period_label"] == hl and pf["period_kind"] == "half_year"
    g = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": pf["confirm_token"],
                                                     "entity_id": grp, "obligation_id": half[0]["obligation_id"]})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    row = s.execute(text("""SELECT f.period_kind, f.period_label, s.payload -> '_period' AS period, s.payload -> '_filer' AS filer
                            FROM regulatory_filing f JOIN report_snapshots s ON s.snapshot_id = f.snapshot_id
                            WHERE f.filing_id = CAST(:f AS uuid)"""), {"f": fid}).mappings().one()
    assert (row["period_kind"], row["period_label"]) == ("half_year", hl)
    assert row["period"] == P.view(h, "half_year")
    assert row["filer"]["frequency"] == "semiannual" and row["filer"]["half_year"] is True
    form = api.get(f"/v1/filings/{fid}", headers=maker).json()
    assert form["due_date"] == due and form["period_kind"] == "half_year"
    secs = {x.get("key"): x for x in api.get(f"/v1/filings/{fid}/form", headers=maker).json()["annex"]["sections"]}
    period = {r["cells"][0]["text"]: r["cells"][1]["text"] for r in secs["period"]["rows"]}
    day = lambda d: f"{d.day} {d:%B %Y}"                                                 # noqa: E731
    assert period == {"Disclosure reference date": day(h),
                      "Reference period": f"{day(P.start(h, P.HALF_YEAR))} to {day(h)} · First half of the financial year",
                      "How often it discloses": "Twice a year — at the half-year and the year end"}
    sizes = {r["cells"][0]["text"]: r["cells"] for r in secs["large_institution"]["rows"]}
    assert sizes["Meridian Financial Group"][2]["frozen_value"] == "listed"
    assert sizes["Meridian Bank AG"][3]["text"].startswith("Once a year")
    assert [o for o in api.get("/v1/obligations", headers=maker).json()["obligations"]
            if o["period_kind"] == "half_year"][0]["filing_id"] == fid
    # the group's Pillar 3 indicators: the half-year filing is a point of its own in the filed trend, in date order, and
    # the board names the half-year (services.governance.kri_scope)
    kri = api.get(f"/v1/reg-tasks/kri?framework=bank_p3esg&entity_id={grp}&role=consolidated", headers=maker)
    assert kri.status_code == 200, kri.text
    labels = [h["label"] for h in kri.json()["history"]]
    i = labels.index(f"{hl} v1")
    assert all(not x.startswith(fyl) for x in labels[:i])                # the years before come before the half-year
    assert all(x.startswith(fyl) for x in labels[i:])

    # 5 · the EBA data hub package for the half-year: its reference date, the group's consolidated situation
    lei = _lei("TESTLEI0P3SEMIANN0")
    s.execute(text("UPDATE reporting_entities SET lei = :l, country = 'DE' WHERE entity_id = CAST(:e AS uuid)"), {"l": lei, "e": grp})
    r = api.get(f"/v1/filings/{fid}/export?format=xbrlcsv", headers=maker)
    assert r.status_code == 200, r.text
    name = re.search(r'filename="([^"]+)"', r.headers["content-disposition"]).group(1)
    assert re.fullmatch(rf"{lei}\.CON_DE_PILLAR3020100_ESGDIS_{h.isoformat()}_\d{{17}}\.zip", name), name
    (tmp_path / name).write_bytes(r.content)
    problems, m = filing_rules(str(tmp_path / name))
    assert problems == [] and m["module"]["version"] == "2.1.0"
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        params = z.read(next(n for n in z.namelist() if n.endswith("reports/parameters.csv"))).decode()
    assert f"refPeriod,{h.isoformat()}" in params

    # 6 · the year end: the year's report is owed beside the half-year's, which stays matched to its filing; the
    # half-year's obligation cannot be prepared while the period is the year
    upsert_reporting_settings(s, BANK_ORG, {"reporting_period_end": fy.isoformat(), "reporting_period_kind": "financial_year"},
                              None)
    cal = api.get("/v1/obligations", headers=maker).json()["obligations"]
    mine = {(o["period_label"], o["filing_role"]): o for o in cal if o["framework"] == "bank_p3esg" and o["entity_id"] == grp}
    assert {fyl, hl} <= {k[0] for k in mine}
    assert mine[(hl, "consolidated")]["filing_id"] == fid and mine[(fyl, "consolidated")]["filing_id"] is None
    r = api.post("/v1/filings", headers=maker, json={"framework": "bank_p3esg", "confirm_token": "x", "entity_id": grp,
                                                     "obligation_id": half[0]["obligation_id"]})
    assert r.status_code == 409 and r.json()["error"]["error"] == "filing.refused.obligation_other_period", r.text


def test_the_orsas_undated_obligation_and_a_half_year_obligation_side_by_side(session_rolled_back):
    """Main's E353 owes the ORSA with no calendar date (its conclusion gives one); E354 owes a semi-annual filer its
    half-year with a date. Both through the one calendar: neither takes the other's shape."""
    from services.governance import filings as F
    s = session_rolled_back
    bank = _org(s)
    insurer = str(uuid.uuid4())
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (CAST(:o AS uuid), :n, 'insurer', 'ES')"),
              {"o": insurer, "n": f"ORSA test {insurer[:8]}"})
    for org in (bank, insurer):
        upsert_reporting_settings(s, org, {"reporting_period_end": "2026-12-31"}, None)
    _state(s, bank, "large_institution", "gsii", bank, H1)
    orsa = [o for o in F.list_obligations(s, insurer, "insurer") if o["framework"] == "insurer_orsa_climate"]
    half = [o for o in F.list_obligations(s, bank, "bank") if o["period_kind"] == "half_year"]
    assert [(o["period_label"], o["period_kind"], o["due_date"], o["days_to_due"]) for o in orsa] == [
        ("FY2026", "financial_year", None, None)]
    assert "2 weeks after concluding the assessment" in orsa[0]["due_rule"]
    assert [(o["period_label"], o["due_date"], o["frequency"]) for o in half] == [("FY2026-H1", "2026-09-30", "semiannual")]
    # the database keeps them apart: no half-year ORSA, no half-year without its date
    for framework, end, kind, label, due in (("insurer_orsa_climate", H1, "half_year", "FY2026-H1", None),
                                              ("bank_p3esg", H1, "half_year", "FY2026-H1", None)):
        with pytest.raises(IntegrityError), s.begin_nested():
            s.execute(text("""INSERT INTO regulatory_obligation (org_id, framework, period_end, period_kind, period_label,
                                                                 due_date, frequency, filing_role)
                              VALUES (CAST(:o AS uuid), :f, :e, :k, :l, :d, 'semiannual', 'whole_org')"""),
                      {"o": insurer if framework.startswith("insurer") else bank, "f": framework, "e": end, "k": kind,
                       "l": label, "d": due})
