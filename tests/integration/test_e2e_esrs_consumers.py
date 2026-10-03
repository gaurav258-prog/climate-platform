"""What reads the ESRS statement, end to end through the HTTP API in one rolled-back transaction (Terra Foods SA, FY2025,
the same set-up as test_e2e_esrs_statement):

  mandate      the CSRD mandate is judged per undertaking from data/reference/csrd/scope.json (Art. 5(2)), not from the
               organisation's PIE / headcount attributes; its deadline reads the undertaking's attested issuer status —
               4 months for an issuer (Directive 2004/109/EC Art. 4(1)), else 12 months at the latest (Directive
               2013/34/EU Art. 30(1)); no fact, no date. The filing calendar follows the facts.
  KRIs         the ESRS KRI set is the statement's own figures for the undertaking, tagged with the printing item; the
               retired E1 / nature KRIs (COGS, sourcing plots, 'near' protected areas) are gone
  supervisors  the national authority's questions are answered by those figures
  prior filing a filed ESRS statement is read line by line onto the concepts its year's version prints (exact label only),
               each concept once; the retired E1 upload takes no new file
"""
from __future__ import annotations

import io

import pytest
from sqlalchemy import text

from tests.integration.test_e2e_esrs_statement import (
    TERRA,
    _approve,
    _period,
    _state,
    _users,
    undertaking,
)

pytestmark = pytest.mark.integration
PE = "2025-12-31"


def _statement_ready(api, maker, checker) -> str:
    """A new undertaking (a copy of Terra Foods SA, E140) with the FY2025 facts its statement needs."""
    s = api.s
    FOODS = undertaking(api)  # noqa: N806
    _period(api, PE)
    for sid in s.execute(text("SELECT site_id::text FROM sc_company_sites WHERE entity_id = CAST(:e AS uuid)"), {"e": FOODS}).scalars():
        for m, v in (("carrying_amount", 5e6), ("net_revenue", 20e6)):
            s.execute(text("""INSERT INTO site_period_values (org_id, site_id, reporting_entity_id, period_end, measure, amount,
                                                              currency, amount_eur, source)
                              VALUES (CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS uuid), :pe, :m, :a, 'EUR', :a, 'client')"""),
                      {"o": TERRA, "s": sid, "e": FOODS, "pe": PE, "m": m, "a": v})
    r = api.post("/v1/periods/role", headers=maker, json={"period_end": PE, "entity_id": FOODS, "role": "individual"})
    assert r.status_code == 202, r.text
    _approve(api, checker, r.json()["approval_request_id"])
    for key, v, extra in (("csrd.large_undertaking", 1, {}), ("csrd.public_interest_entity", 1, {}),
                          ("csrd.employees_average", 1200, {}), ("csrd.net_turnover", 500e6, {"currency": "EUR"}),
                          ("esrs.method.physical_risk_level", 30, {}), ("fs.total_assets", 200e6, {"currency": "EUR"}),
                          ("fs.net_revenue", 400e6, {"currency": "EUR"}), ("e1.ghg.scope1.gross", 1234, {})):
        _state(api, maker, checker, PE, key, v, **extra)
    return FOODS


def _esrs(obligations, entity_id):
    """The undertaking's own ESRS obligations — the organisation's other undertakings hold whatever the live database
    gives them (E140)."""
    return [o for o in obligations if o["framework"] == "esrs_pack" and o["entity_id"] == entity_id]


def test_the_mandate_calendar_kris_and_supervisors_read_the_statement(api):
    maker, checker = _users(api)
    FOODS = _statement_ready(api, maker, checker)  # noqa: N806

    # ── the mandate: Art. 5(2) per undertaking; no deadline until the issuer status is stated ──
    mm = {m["id"]: m for m in api.get("/v1/me/supervisors/mandates", headers=maker).json()["mandates"]}["csrd_esrs_e1"]
    assert mm["status"] == "applies" and mm["deliverable"]["due"] is None
    foods = next(u for u in mm["undertakings"] if u["entity_id"] == FOODS)
    assert foods["required"] is True and foods["point"] == "a_i" and foods["issuer"] is None
    others = [u for u in mm["undertakings"] if u["entity_id"] != FOODS]
    assert others and all(u["required"] is None for u in others if u["role"] is None)   # role not stated: not guessed
    assert all(u["required"] is False for u in others if u["role"] == "exempt_subsidiary")
    assert not {"public_interest_entity", "employees"} & {c["attribute"] for c in mm["checks"]}
    assert _esrs(api.get("/v1/obligations", headers=maker).json()["obligations"], FOODS) == []

    _state(api, maker, checker, PE, "csrd.transparency_issuer", 1)
    ob = _esrs(api.get("/v1/obligations", headers=maker).json()["obligations"], FOODS)
    assert [(o["entity_id"], o["due_date"], o["filing_role"]) for o in ob] == [(FOODS, "2026-04-30", "solo")]
    mm = {m["id"]: m for m in api.get("/v1/me/supervisors/mandates", headers=maker).json()["mandates"]}["csrd_esrs_e1"]
    assert mm["deliverable"]["due"] == "2026-04-30"
    _state(api, maker, checker, PE, "csrd.transparency_issuer", 0)        # restated: not an issuer → Art. 30(1)
    ob = _esrs(api.get("/v1/obligations", headers=maker).json()["obligations"], FOODS)
    assert [(o["entity_id"], o["due_date"]) for o in ob] == [(FOODS, "2026-12-31")]

    # ── the KRIs: the statement's own figures for the undertaking ──
    st = api.get(f"/v1/esrs/statement?entity_id={FOODS}", headers=maker).json()["document_report"]["statement"]["concepts"]
    d = api.get(f"/v1/reg-tasks/kri?framework=esrs_pack&entity_id={FOODS}", headers=maker).json()
    assert d["supported"] and d["undertaking"]["entity_id"] == FOODS and d["undertaking"]["esrs_version"] == "dr_2023_2772_as_2025_1416"
    k = {x["key"]: x for x in d["kpis"]}
    assert k["e1.physrisk.assets.amount"]["value"] == st["e1.physrisk.assets.amount"]["value"]
    assert k["e1.physrisk.assets.amount"]["kind"] == "computed" and k["e1.physrisk.assets.amount"]["reg"].startswith("ESRS E1-9.66a")
    assert k["fs.total_assets"]["value"] == 200e6 and k["fs.total_assets"]["kind"] == "integrated"
    assert k["e1.ghg.scope1.gross"]["value"] == 1234 and k["e3.water.consumption"]["value"] is None   # not stated: a gap
    assert not {"asset_at_risk", "cogs_at_risk", "water_plots_stressed", "protected_area", "frost_severity"} & set(k)
    assert d["by_hazard"] and all(0 < h["value"] <= 15e6 for h in d["by_hazard"])
    det = api.get(f"/v1/reg-tasks/kri/detail?framework=esrs_pack&kri=e1.physrisk.assets.amount&entity_id={FOODS}", headers=maker).json()
    assert "physical_risk_level" in det["methodology"] and det["composition"]["type"] == "hazard"
    hz = api.get(f"/v1/reg-tasks/kri/hazard?framework=esrs_pack&entity_id={FOODS}&hazard={d['by_hazard'][0]['hazard']}", headers=maker).json()
    assert hz["entities"] and hz["entities"][0]["value"] <= 5e6
    assert api.get("/v1/reg-tasks/kri?framework=csrd_e1", headers=maker).json()["supported"] is False     # retired
    from services.governance.reg_impact_links import links_for
    # a detected ESRS change names these KRIs
    assert {"e1.physrisk.assets.amount", "e4.sites.sensitive.count"} <= {x["key"] for x in links_for("esrs_pack")["kris"]}

    # ── the national authority's questions, answered by the statement's figures ──
    # several undertakings prepare a statement (the demo's own and this one): none is chosen for the ESRS questions, the
    # choice is listed (E141); a malformed undertaking id is refused at the boundary
    whole = api.get("/v1/reg-tasks/supervisory", headers=maker).json()
    if len(whole["esrs"]["undertakings"]) > 1:
        assert whole["esrs"]["undertaking"] is None and FOODS in {u["entity_id"] for u in whole["esrs"]["undertakings"]}
    assert api.get("/v1/reg-tasks/supervisory?entity_id=nope", headers=maker).status_code == 422
    sup = api.get(f"/v1/reg-tasks/supervisory?entity_id={FOODS}", headers=maker).json()
    assert sup["esrs"]["undertaking"]["entity_id"] == FOODS
    nca = next(x for x in sup["supervisors"] if x["id"] == "nca_sustainability")
    q = {x["question"]: x for x in nca["questions"]}
    assets_q = next(v for kq, v in q.items() if "material physical risk, before adaptation" in kq)
    assert assets_q["answer"]["value"] == st["e1.physrisk.assets.amount"]["value"]
    assert not any("COGS" in kq or "sourcing" in kq.lower() for kq in q)


def _xlsx(rows):
    import openpyxl
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(api, who, framework, label, rows, **form):
    return api.post("/v1/prior-filings/upload", headers=who, data={"framework": framework, "period_label": label, **form},
                    files={"file": ("statement.xlsx", _xlsx(rows), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


def test_a_filed_esrs_statement_is_read_onto_its_years_concepts(api):
    maker, _ = _users(api)
    assert "csrd_e1" not in {f["key"] for f in api.get("/v1/prior-filings/frameworks", headers=maker).json()["frameworks"]}
    old = _upload(api, maker, "csrd_e1", "FY2024", [("Gross Scope 1 GHG emissions", 1)], period_end="2024-12-31",
                  undertaking="organisation")
    assert old.status_code == 400 and "no new filings" in old.text
    undated = _upload(api, maker, "esrs_pack", "FY2024", [("Gross Scope 1 GHG emissions", 1)], undertaking="organisation")
    assert undated.status_code == 400 and "period ends" in undated.text                      # stated, never read from the label
    nobody = _upload(api, maker, "esrs_pack", "FY2024", [("Gross Scope 1 GHG emissions", 1)], period_end="2024-12-31")
    assert nobody.status_code == 400 and "whom the filed report is for" in nobody.text
    before = _upload(api, maker, "esrs_pack", "FY2023", [("Gross Scope 1 GHG emissions", 1)], period_end="2023-12-31",
                     undertaking="organisation")
    assert before.status_code == 400 and "no ESRS version" in before.text                    # FY2023: no ESRS applies

    r = _upload(api, maker, "esrs_pack", "FY2024", [("Gross Scope 1 GHG emissions (tCO2eq)", 1500),
                                                    ("Total water consumption", 42000),
                                                    ("GHG emissions scope 1 and energy", 9)], period_end="2024-12-31", undertaking="organisation")
    assert r.status_code == 201, r.text
    f = r.json()
    lines = {x["label"]: x for x in f["figures"]}
    assert lines["Gross Scope 1 GHG emissions (tCO2eq)"]["datapoint_key"] == "e1.ghg.scope1.gross"
    assert lines["Total water consumption"]["datapoint_key"] == "e3.water.consumption"
    assert lines["GHG emissions scope 1 and energy"]["datapoint_key"] is None                 # no keyword guess
    opts = api.get(f"/v1/prior-filings/datapoints/esrs_pack?period_end={f['period_end']}", headers=maker).json()["datapoints"]
    keys = {o["key"] for o in opts}
    assert "e1.physrisk.assets.amount" in keys and "e1.ghg.scope3.by_category" not in keys    # a breakdown is not one line
    assert not any(k.endswith(".v2026") for k in keys)                                        # FY2024: the 2023 standards

    stray = lines["GHG emissions scope 1 and energy"]["figure_id"]
    twice = api.post(f"/v1/prior-filings/{f['filing_id']}/confirm", headers=maker,
                     json={"edits": [{"figure_id": stray, "datapoint_key": "e1.ghg.scope1.gross"}]})
    assert twice.status_code in (400, 422) and "more than one line" in twice.text
    legacy = api.post(f"/v1/prior-filings/{f['filing_id']}/confirm", headers=maker,
                      json={"edits": [{"figure_id": stray, "datapoint_key": "e1_ghg"}]})
    assert legacy.status_code in (400, 422) and "e1_ghg" in legacy.text
    ok = api.post(f"/v1/prior-filings/{f['filing_id']}/confirm", headers=maker, json={"edits": [{"figure_id": stray, "drop": True}]})
    assert ok.status_code == 200, ok.text
    series = {s["datapoint_key"]: s for s in api.get("/v1/prior-filings/trends?framework=esrs_pack", headers=maker).json()["series"]}
    assert series["e1.ghg.scope1.gross"]["label"] == "Gross Scope 1 GHG emissions"
    assert series["e1.ghg.scope1.gross"]["points"][0]["value"] == 1500
