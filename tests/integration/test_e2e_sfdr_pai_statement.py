"""The entity's principal adverse impacts statement for a reference period, end to end through the HTTP API in one
rolled-back transaction (Nordkap Asset Management, whose two funds hold positions on the four quarter ends of 2025):

  Art. 4(1)   a statement covers 1 January - 31 December: another period end is refused
  Art. 6(3)   every impact is the average of the impacts on 31 March, 30 June, 30 September and 31 December
  Art. 5-9    each item of the sections is answered for the period; a computed item, a future approval date, a scenario
              used without its name, a host-Member-State language without the State, an unknown item are refused (nothing
              stored); what is still required is listed by Article point and blocks the filing
  col. d      Impact [year n-1] is the figure reported for the previous period — a previous statement uploaded, stated as
              the organisation's and for 31 December 2024, and confirmed; Art. 10 compares with it
  freeze      the statement freezes its answers: the form, the annex sections and the xlsx print them, and a later
              change of answer does not reach the filed statement; four eyes, attestation, submission
  next year   the 2026 statement's previous period is the filed 2025 statement (preferred over an upload); a quarter end
              without holdings is named
"""
from __future__ import annotations

import io
from datetime import date

import pytest
from sqlalchemy import text

from services.governance import template_answers as T
from tests.integration.conftest import login as _login
from tests.integration.test_e2e_esrs_consumers import _upload
from tests.integration.test_e2e_sfdr_pai_precontractual import (
    NORDKAP,
    _file_and_submit,
    _set_aside,
    _users,
)

pytestmark = pytest.mark.integration
DATES = ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")


def _answers(rows: list[dict]) -> dict:
    a = {
        "S1.d_summary": {"rows": [
            {"d_language": "no", "d_meets": ["home_official"], "d_text": "Sammendrag av de viktigste negative virkningene."},
            {"d_language": "en", "d_meets": ["international_finance"], "d_text": "Summary of the principal adverse impacts."}]},
        "S4.policies": {"text": "Our policy identifies PAIs by sector exposure and is reviewed yearly."},
        "S4.a_approval_date": {"text": "2025-03-14"},
        "S4.b_responsibility": {"text": "The CIO implements it; the risk committee oversees it."},
        "S4.c_methodologies": {"text": "Severity by sector intensity, probability by data coverage."},
        "S4.d_margin_of_error": {"text": "Estimated figures carry the sector-average error."},
        "S4.e_data_sources": {"text": "Issuer reports and one data provider."},
        "S4.best_efforts": {"text": "Requested missing data from every investee and two providers."},
        "S5.a_srd": {"applicable": False},
        "S5.b_other": {"text": "We engage the ten largest emitters each year."},
        "S5.2a_indicators": {"text": "Indicators 1 to 4."},
        "S5.2b_adaptation": {"text": "Escalation to a vote against after two periods without reduction."},
        "S6.adherence": {"text": "We adhere to the OECD Guidelines for Multinational Enterprises."},
        "S6.2a_indicators": {"text": "Indicators 10 and 11."},
        "S6.2b_methodology": {"text": "Controversy screening of every holding, quarterly."},
        "S6.2c_scenario": {"ticked": False},
        "S6.2d_no_scenario": {"text": "Our holding period is shorter than any scenario's horizon."},
    }
    for r in rows:
        a[f"{r['key']}.expl"] = {"text": f"Explained: {r['key']}"}
        a[f"{r['key']}.action"] = {"text": f"Action: {r['key']}"}
    return a


def test_the_statement_for_a_reference_period(api):
    maker, checker = _users(api)
    s = api.s
    _set_aside(s, "sfdr_pai")

    # Art. 4(1): a reference period ends on a 31 December
    bad = api.get("/v1/entity/sfdr-statement?period_end=2025-06-30", headers=maker)
    assert bad.status_code == 422 and "Article 4(1)" in bad.text

    # Art. 6(3): the four quarter ends, averaged — the value in scope independently from the holdings themselves
    st = api.get("/v1/entity/sfdr-statement?period_end=2025-12-31", headers=maker).json()
    assert st["reference_period"]["impact_dates"] == list(DATES)
    sums = [s.execute(text("""SELECT sum(market_value_eur) FROM fund_positions p JOIN funds f USING (fund_id)
                              WHERE f.org_id = CAST(:o AS uuid) AND p.as_of_date = :d"""), {"o": NORDKAP, "d": d}).scalar()
            for d in DATES]
    assert st["entity"]["total_value_eur"] == pytest.approx(float(sum(sums)) / 4)
    pai1 = st["indicators"][0]
    quarters = [q["value"]["total"] for q in pai1["quarters"]]
    assert [q["date"] for q in pai1["quarters"]] == list(DATES)
    assert pai1["value"]["total"] == pytest.approx(sum(quarters) / 4) and len(set(quarters)) > 1
    live = api.get("/v1/entity/sfdr-statement", headers=maker).json()
    assert live["reference_period"] is None and not live["filing_readiness"]["ready_to_file"]   # a live view is never filed

    a = api.get("/v1/entity/pai-statement/answers?period_end=2025-12-31", headers=maker).json()
    assert a["prior_period"] is None and not a["historical_comparison"]["applies"]
    assert {"Article 5(d)", "Article 7(1)(a)", "Article 9(2)(c)"} <= {m.split(":")[0] for m in a["missing"]}
    assert [sec["id"] for sec in a["sections"]] == ["S1", "S4", "S5", "S6", "S7"]

    # refusals: nothing is stored
    for wrong, why in (({"S1.a_name": {"text": "x"}}, "computed"),
                       ({"S4.a_approval_date": {"text": "2999-01-01"}}, "future"),
                       ({"S6.2c_scenario": {"ticked": True}}, "name, its provider"),
                       ({"S1.d_summary": {"rows": [{"d_language": "de", "d_meets": ["host_official"], "d_text": "x"}]}},
                        "host Member State"),
                       ({"S9.anything": {"text": "x"}}, "no such item")):
        r = api.put("/v1/entity/pai-statement/answers", headers=maker, json={"period_end": "2025-12-31", "answers": wrong})
        assert r.status_code == 422 and why in r.text, (wrong, r.text)
    assert T.read(s, NORDKAP, "sfdr_pai", "pai_statement", period_end=date(2025, 12, 31)) == {}

    # the previous period: a statement published for 2024, uploaded, stated as the organisation's, confirmed
    up = _upload(api, maker, "sfdr_pai", "FY2024", [("indicator.2", 61.5), ("indicator.1", 30000)],
                 period_end="2024-12-31", undertaking="organisation")
    assert up.status_code == 201, up.text
    assert {x["datapoint_key"] for x in up.json()["figures"]} == {"indicator.1", "indicator.2"}
    assert api.post(f"/v1/prior-filings/{up.json()['filing_id']}/confirm", headers=maker, json={}).status_code == 200
    a = api.get("/v1/entity/pai-statement/answers?period_end=2025-12-31", headers=maker).json()
    rows = {r["key"]: r for r in a["rows"]}
    assert rows["indicator.2"]["prior"] == 61.5 and rows["indicator.1"]["prior"] == 30000
    assert a["prior_period"]["source"] == "previous statement uploaded and confirmed"
    assert a["historical_comparison"]["applies"]

    # every answer the Regulation requires
    r = api.put("/v1/entity/pai-statement/answers", headers=maker,
                json={"period_end": "2025-12-31", "answers": _answers(a["rows"])})
    assert r.status_code == 200, r.text
    a = api.get("/v1/entity/pai-statement/answers?period_end=2025-12-31", headers=maker).json()
    assert a["missing"] == [] and a["ready_to_file"], a["missing"]

    # freeze, check, print
    pf = api.get("/v1/filings/preflight?framework=sfdr_pai", headers=maker).json()
    assert pf["confirm_token"]
    g = api.post("/v1/filings", headers=maker, json={"framework": "sfdr_pai", "confirm_token": pf["confirm_token"]})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    v = api.get(f"/v1/filings/{fid}/validation", headers=maker).json()
    assert v["passed"], [f for f in v["findings"] if not f["passed"] and f["severity"] == "blocking"]
    assert {"reference_period", "holdings_on_impact_dates", "sections_answered"} <= {f["rule"] for f in v["findings"]}

    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    secs = {x["key"]: x for x in form["annex"]["sections"]}
    assert ["sfdr_s1", "sfdr_t1_1"] == [x["key"] for x in form["annex"]["sections"]][:2]
    assert {"sfdr_s4", "sfdr_s5", "sfdr_s6", "sfdr_s7"} <= set(secs)
    t1 = [row for k, sec in secs.items() if k.startswith("sfdr_t1") for row in sec["rows"] if row["type"] == "row"]
    carbon = next(row for row in t1 if "Carbon footprint" in row["cells"][0]["text"])
    assert carbon["cells"][3]["dp"]["value"] == 61.5 and carbon["cells"][4]["text"] == "Explained: indicator.2"
    assert "the average of the impacts on 2025-03-31" in secs["sfdr_t1_1"]["note"]
    s5 = {row["cells"][0]["text"]: row["cells"][1]["text"] for row in secs["sfdr_s5"]["rows"] if row["type"] == "row"}
    assert next(v for k, v in s5.items() if k.startswith("(a) where applicable")) == "Not applicable (stated)"
    assert any("2024-12-31 · indicator.2" == row["cells"][0]["text"] for row in secs["sfdr_s7"]["rows"] if row["type"] == "row")

    # a later change of answer does not reach the frozen statement
    api.put("/v1/entity/pai-statement/answers", headers=maker,
            json={"period_end": "2025-12-31", "answers": {"indicator.2.expl": {"text": "Changed after freezing."}}})
    form2 = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    assert "Changed after freezing." not in str(form2["annex"])

    x = api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker)
    assert x.status_code == 200
    import openpyxl
    sheet = openpyxl.load_workbook(io.BytesIO(x.content))["Computed disclosure"]
    cells = {str(c.value) for row in sheet.iter_rows() for c in row if c.value is not None}
    assert "Explained: indicator.2" in cells and "61.5" in cells
    assert any("the average of the impacts on 2025-03-31" in c for c in cells)                 # section notes travel
    assert any(c.startswith("(e) the data sources used") for c in cells)
    assert api.get(f"/v1/filings/{fid}/export?format=xbrl", headers=maker).status_code == 409    # no SFDR XBRL (E113)
    _file_and_submit(api, maker, checker, fid, "I approve the 2025 PAI statement.")

    # the next year: the previous period is the filed statement; a quarter end without holdings is named
    n = api.get("/v1/entity/pai-statement/answers?period_end=2026-12-31", headers=maker)
    if n.status_code == 200:
        nx = n.json()
        assert nx["prior_period"]["source"].startswith("statement filed") and nx["prior_period"]["filing_id"] == fid
        assert any(m.startswith("holdings: ") and "2026-03-31" in m for m in nx["missing"])
    else:                                            # no position on file for any date of 2026
        assert n.status_code == 409


def test_the_old_narratives_are_retired_and_shown_only_for_reference(api):
    maker = _login(api, "admin@nordkap.demo", "Demo!admin1")
    r = api.put("/v1/manager/filing-profile", headers=maker, json={"lei": "9695003YCOLOMW6OMD54", "narratives": {"policies": "x"}})
    assert r.status_code == 422 and "per reference period" in r.text
    assert "sfdr_narratives" not in api.get("/v1/manager/filing-profile", headers=maker).json()
    T.save(api.s, NORDKAP, "sfdr_pai", "pai_statement", {"items": [{"id": "policies", "kind": "field"}]},
           {"policies": "input"}, {"policies": {"text": "An earlier text."}}, None)
    a = api.get("/v1/entity/pai-statement/answers?period_end=2025-12-31", headers=maker).json()
    assert a["legacy_narratives"]["policies"] == "An earlier text."
    assert "policies" not in a["answers"] and any(m.startswith("Article 7(1)") for m in a["missing"])
