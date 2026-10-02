"""The ESRS statement, end to end through the HTTP API, in one rolled-back transaction (Terra Foods SA, an undertaking of
Terra Group; analyst = maker, approver = checker):

  FY2025   version: 2025/1416-amended ESRS (the financial year starts in 2025)
           who      the role is stated (individual, four eyes); Art. 5(2)(a) point (i) reads the undertaking's stated
                    facts: large, PIE, 1 200 employees (> 500) → required; neither the €450m nor the 1 000-employee
                    figure is not exceeded, so the Member State derogation cannot apply
           figures  the year-end book (3 sites × carrying 5m / net revenue 20m) and the stated figures (total assets,
                    net revenue, the materiality level) → E1-9 assets at material physical risk computed per horizon
           items    E1 material, E3 and E4 not (with the explanation); a phase-in the undertaking does not qualify for
                    (1 200 employees > 750) is refused; every other item filled or omitted with its reason
           filing   the period is closed (four eyes); the pre-filing check, the frozen statement (its checks pass), the
                    official form item by item, JSON only (no ESRS XBRL), maker/checker, attestation, submission
           comparatives (2023 ESRS 1 §83, §85): a FY2025 figure needs its FY2024 comparative (second year of a wave-one
           undertaking) — the undertaking discloses it is impracticable
  FY2026   the comparative is the figure the filed FY2025 statement reported; an attested revision of it needs the
           reasons (§84) and prints the difference
  FY2027   version: Delegated Regulation (EU) 2026/1563; Art. 5(2)(b) needs that year's turnover and headcount (an
           amount is stated once its year end has passed)
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"
FOODS = "e304ce79-c45c-45a5-9f93-8f6bb9f76dc7"          # Terra Foods SA — holds the Lisbon, Madrid and Seville sites


def _users(api):
    return _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")


def _approve(api, checker, rid):
    r = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": "checked"})
    assert r.status_code == 200, r.text


def _state(api, maker, checker, pe, key, value, **extra):
    r = api.post("/v1/provided", headers=maker, json={"framework": "esrs", "datapoint_key": key, "value_num": value,
                                                      "reporting_period_end": pe, "reporting_entity_id": FOODS, **extra})
    assert r.status_code == 201, r.text
    _approve(api, checker, r.json()["approval_request_id"])


def _period(api, pe):
    api.s.execute(text("""INSERT INTO org_reporting_settings (org_id, reporting_period_end) VALUES (CAST(:o AS uuid), :pe)
                          ON CONFLICT (org_id) DO UPDATE SET reporting_period_end = EXCLUDED.reporting_period_end"""),
                  {"o": TERRA, "pe": pe})


def _statement(api, who):
    r = api.get(f"/v1/esrs/statement?entity_id={FOODS}", headers=who)
    assert r.status_code == 200, r.text
    return r.json()


def _failing(d, severity="blocking"):
    return {c["rule"]: c["message"] for c in d["checks"] if not c["passed"] and c["severity"] == severity}


def _answer(api, who, standard, answers):
    r = api.put("/v1/esrs/answers", headers=who, json={"standard": standard, "answers": answers, "entity_id": FOODS})
    assert r.status_code == 200, r.text
    return r.json()


def test_an_undertaking_states_files_and_carries_forward_its_esrs_statement(api):
    maker, checker = _users(api)
    s = api.s
    _period(api, "2025-12-31")
    sites = s.execute(text("SELECT site_id::text FROM sc_company_sites WHERE entity_id = CAST(:e AS uuid) ORDER BY name"),
                      {"e": FOODS}).scalars().all()
    assert len(sites) == 3
    for sid in sites:
        for m, v in (("carrying_amount", 5e6), ("net_revenue", 20e6)):
            s.execute(text("""INSERT INTO site_period_values (org_id, site_id, reporting_entity_id, period_end, measure, amount,
                                                              currency, amount_eur, source)
                              VALUES (CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS uuid), '2025-12-31', :m, :a, 'EUR', :a, 'client')"""),
                      {"o": TERRA, "s": sid, "e": FOODS, "m": m, "a": v})

    # ── FY2025 · who reports, and must it ──
    d = _statement(api, maker)
    assert d["spec"]["version"] == "dr_2023_2772_as_2025_1416"
    assert "csrd_role" in _failing(d) and {"materiality_E1", "materiality_E3", "materiality_E4"} <= set(_failing(d))
    r = api.post("/v1/periods/role", headers=maker, json={"period_end": "2025-12-31", "entity_id": FOODS, "role": "individual"})
    assert r.status_code == 202, r.text
    _approve(api, checker, r.json()["approval_request_id"])
    assert _statement(api, maker)["document_report"]["scope_check"]["missing"]         # the facts are not stated yet
    for key, v, extra in (("csrd.large_undertaking", 1, {}), ("csrd.public_interest_entity", 1, {}),
                          ("csrd.employees_average", 1200, {}), ("csrd.net_turnover", 500e6, {"currency": "EUR"}),
                          ("csrd.first_reporting_year", 2024, {}), ("esrs.method.physical_risk_level", 30, {}),
                          ("fs.total_assets", 200e6, {"currency": "EUR"}), ("fs.net_revenue", 400e6, {"currency": "EUR"})):
        _state(api, maker, checker, "2025-12-31", key, v, **extra)
    d = _statement(api, maker)
    sc = d["document_report"]["scope_check"]
    assert sc["required"] is True and sc["point"] == "a_i" and "derogation" not in sc
    assert "csrd_role" not in _failing(d) and "csrd_scope" not in _failing(d, "warning")

    # ── the figures: computed from the year-end book at the stated level ──
    c = d["document_report"]["statement"]["concepts"]
    assets = c["e1.physrisk.assets.amount"]
    short = assets["by_horizon"]["short"]
    assert short is not None and 0 < short <= 15e6                                  # at most the 3 sites' 15m
    assert abs(c["e1.physrisk.assets.pct"]["by_horizon"]["short"] - short / 200e6 * 100) < 1e-6   # of the stated total assets
    # heat is scored today at every site but has no SSP5-8.5 projection: the medium and long terms are not known
    assert assets["by_horizon"]["medium"] is None and assets["by_horizon"]["long"] is None
    assert assets["status"] == "gap" and "heat_chronic at Seville processing plant" in assets["gap"]

    # ── materiality, then every item of E1 ──
    refused = api.put("/v1/esrs/answers", headers=maker, json={"standard": "materiality", "entity_id": FOODS,
                                                                 "answers": {"E1": {"material": False}}})
    assert refused.status_code == 422 and "detailed explanation" in refused.text              # climate change: explain
    _answer(api, maker, "materiality", {"E1": {"material": True},
                                        "E3": {"material": False, "explanation": "no water-intensive operations"},
                                        "E4": {"material": False, "explanation": "no sites in or near sensitive areas"}})
    d = _statement(api, maker)
    e1 = next(x for x in d["document_report"]["sections"] if x["standard"] == "E1")
    assert all(i["status"] == "omitted" for x in d["document_report"]["sections"] if x["standard"] != "E1"
               for i in x["items"] if i["status"] != "printed")
    bad = api.put("/v1/esrs/answers", headers=maker, json={"standard": "E1", "entity_id": FOODS, "answers": {
        "E1-6.44c": {"omitted": {"reason": "condition_not_applicable", "statement": "x"}}}})
    assert bad.status_code == 422 and "no printed condition" in bad.text
    _answer(api, maker, "E1", {"E1-6.44c": {"omitted": {"reason": "phase_in", "phase_in": "e1_6_scope3_total_wave1"}}})
    assert "750 employees" in _failing(_statement(api, maker))["phase_ins"]                  # 1 200 employees: it does not apply
    todo = [i for i in e1["items"] if i["status"] == "missing"]
    physrisk = next(i for i in e1["items"] if any(dp.get("concept") == "e1.physrisk.assets.amount" for dp in i.get("datapoints") or []))
    dr_of, dr = {}, None
    for i in e1["items"]:
        dr = i["id"] if i["kind"] == "heading" else dr
        dr_of[i["id"]] = dr
    answers = {}
    _state(api, maker, checker, "2025-12-31", "e1.energy.total", 1000)                     # E1-5.37, MWh
    for i in todo:
        if i["id"] == "E1-5.37":
            continue
        if dr_of[i["id"]] == "E1-9":            # wave one, second year (first reporting year 2024): the phase-in holds
            answers[i["id"]] = {"omitted": {"reason": "phase_in", "phase_in": "e1_9_first_years_wave1"}}
        elif i["kind"] == "choice":
            answers[i["id"]] = {"ticked": False}
        elif i.get("conditional"):
            answers[i["id"]] = {"omitted": {"reason": "condition_not_applicable", "statement": "the condition does not apply"}}
        else:
            answers[i["id"]] = {"omitted": {"reason": "not_material", "statement": "assessed not material for the undertaking"}}
    answers["E1-6.44c"] = {"omitted": {"reason": "not_material", "statement": "assessed not material for the undertaking"}}
    out = _answer(api, maker, "E1", answers)
    assert not out["refused"], out["refused"][:3]
    d = _statement(api, maker)
    # ESRS 1 §83: the second year of a wave-one undertaking (first 2024) — a comparative for FY2024 is required; none is
    # stated or reported, so it blocks until the undertaking discloses that it is impracticable (§85)
    assert "e1.energy.total" in _failing(d)["comparatives"]
    bad = api.put("/v1/esrs/answers", headers=maker, json={"standard": "comparatives", "entity_id": FOODS,
                                                           "answers": {"cmp.e1.energy.total": {}}})
    assert bad.status_code == 422
    _answer(api, maker, "comparatives", {"cmp.e1.energy.total": {
        "impracticable": "Energy was not metered per site in 2024; it cannot be recreated."}})
    d = _statement(api, maker)
    assert _failing(d) == {}, _failing(d)
    assert set(_failing(d, "warning")) == {"period_closed"}

    # ── close the year, then file ──
    r = api.post("/v1/periods/close", headers=maker, json={"period_end": "2025-12-31", "entity_id": FOODS})
    assert r.status_code == 202, r.text
    _approve(api, checker, r.json()["approval_request_id"])
    assert _statement(api, maker)["document_report"]["period_closed"] is True
    pf = api.get(f"/v1/filings/preflight?framework=esrs_pack&entity_id={FOODS}", headers=maker)
    assert pf.status_code == 200, pf.text
    g = api.post("/v1/filings", headers=maker, json={"framework": "esrs_pack", "confirm_token": pf.json()["confirm_token"],
                                                     "entity_id": FOODS})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    v = api.get(f"/v1/filings/{fid}/validation", headers=maker).json()
    assert v["passed"], [f for f in v["findings"] if not f["passed"] and f["severity"] == "blocking"]
    filed = json.loads(api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).content)
    doc = filed["payload"]["document_report"]
    assert filed["payload"]["_specs"]["esrs"]["version"] == "dr_2023_2772_as_2025_1416"
    assert doc["reporting_entity_id"] == FOODS and doc["period_closed"] and doc["role"]["role"] == "individual"
    assert doc["statement"]["concepts"]["e1.physrisk.assets.amount"]["by_horizon"] == assets["by_horizon"]
    assert api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker).status_code == 409        # no ESRS XBRL
    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    annex = form.get("annex") or {}
    assert [x["key"] for x in annex.get("sections", []) if x.get("kind") == "document"] == ["esrs_E1", "esrs_E3", "esrs_E4"]
    shown = {i["id"]: i for i in annex["sections"][0]["items"]}
    assert dr_of[physrisk["id"]] == "E1-9" and shown[physrisk["id"]]["note"] == "Omitted: phase-in (e1_9_first_years_wave1)"
    sr = api.post(f"/v1/filings/{fid}/submit-for-review", headers=maker)
    assert sr.status_code == 200, sr.text
    _approve(api, checker, sr.json()["approval_request_id"])
    at = api.post(f"/v1/filings/{fid}/attest", headers=checker, json={"statement": "I approve the FY2025 ESRS statement."})
    assert at.status_code == 200, at.text
    assert api.post(f"/v1/filings/{fid}/submit", headers=maker, json={"submission_ref": "OAM-2025-TF"}).status_code == 200

    # ── FY2026: the previous period beside each figure ──
    _period(api, "2026-12-31")
    d = _statement(api, maker)
    cmp_ = d["document_report"]["comparatives"]
    assert cmp_["previous_period_end"] == "2025-12-31" and cmp_["reported"]["filing_id"] == fid   # the filed statement
    _state(api, maker, checker, "2026-12-31", "csrd.first_reporting_year", 2024)
    _state(api, maker, checker, "2026-12-31", "e1.energy.total", 900)
    _answer(api, maker, "materiality", {"E1": {"material": True},
                                        "E3": {"material": False, "explanation": "no water-intensive operations"},
                                        "E4": {"material": False, "explanation": "no sites in or near sensitive areas"}})
    row = next(r for r in _statement(api, maker)["document_report"]["comparatives"]["rows"]
               if r["concept"] == "e1.energy.total")
    assert row["status"] == "comparative" and row["comparative"] == 1000 and row["reported"] == 1000   # as filed for FY2025
    # the undertaking revises the FY2025 figure (2023 ESRS 1 §84): the difference and the reasons are required
    _state(api, maker, checker, "2025-12-31", "e1.energy.total", 1100, restatement_reason="late Seville utility invoice")
    d = _statement(api, maker)
    row = next(r for r in d["document_report"]["comparatives"]["rows"] if r["concept"] == "e1.energy.total")
    assert row["status"] == "reason_missing" and row["difference"] == pytest.approx(100)
    assert "reasons for the revision" in _failing(d)["comparatives"]
    _answer(api, maker, "comparatives", {"cmp.e1.energy.total": {
        "reason": "a 2025 utility invoice for the Seville plant arrived after the statement was filed"}})
    d = _statement(api, maker)
    assert "comparatives" not in _failing(d)
    from services.governance.esrs_document import sections as shown_sections
    e1_shown = {i["id"]: i for i in shown_sections({"document_report": d["document_report"],
                                                    "_specs": {"esrs": d["spec"]}})[0]["items"]}
    printed = e1_shown["E1-5.37"]["value"]["text"]
    assert "revised from 1,000 as reported, difference 100" in printed and "utility invoice" in printed

    # ── FY2027: the 2026 standards and Art. 5(2)(b) ──
    _period(api, "2027-12-31")
    d = _statement(api, maker)
    assert d["spec"]["version"] == "dr_2026_1563"
    r = api.post("/v1/periods/role", headers=maker, json={"period_end": "2027-12-31", "entity_id": FOODS, "role": "individual"})
    _approve(api, checker, r.json()["approval_request_id"])
    sc = _statement(api, maker)["document_report"]["scope_check"]
    assert sc["point"] == "b_i" and sc["required"] is None and set(sc["missing"]) == {"csrd.net_turnover", "csrd.employees_average"}
    _state(api, maker, checker, "2027-12-31", "csrd.employees_average", 1200)
    sc = _statement(api, maker)["document_report"]["scope_check"]
    assert sc["required"] is None and sc["missing"] == ["csrd.net_turnover"]
    early = api.post("/v1/provided", headers=maker, json={"framework": "esrs", "datapoint_key": "csrd.net_turnover",
                                                          "value_num": 500e6, "currency": "EUR", "reporting_period_end": "2027-12-31",
                                                          "reporting_entity_id": FOODS})
    assert early.status_code == 400 and "in the future" in early.text           # an amount is stated once its date has passed
