"""End to end, through the HTTP API: the ORSA climate change scenario analysis (Directive 2009/138/EC Art. 45a, 51(1b)(e)
as inserted by Directive (EU) 2025/2) and the pre-emptive recovery plan's nat-cat stress and capital indicators
(Directive (EU) 2025/1 Art. 5(7)-(8)), for one undertaking.

  ORSA  the undertaking's own funds, SCR and treaty attested (four eyes) → the document computes the two scenarios the
        Article asks for (below 2 °C: SSP1-2.6, 1.8 °C; significantly higher: SSP5-8.5, 4.4 °C) at 2030/2050/2100 on the
        same book, with the capital impact worked from the attested figures; the undertaking answers the rest (an
        interval over three years is refused) → prepared for a conclusion on 31 March 2027, the filing is governed by
        Art. 45a and due two weeks later (Art. 312(1)(b)); made today it is governed by nothing yet and cannot pass
        → four eyes, attestation, submission; the small and non-complex derogation waives the scenario items
  IRRD  the plan's trigger levels attested (below the SCR-breach level refused) → the severe event taken from the
        attested own funds, today and under warming; the SCR-breach indicator always present; the triggers crossed
        worked by hand → filed and checked

Every test runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import json

import pytest

from tests.integration.conftest import login as _login
from tests.integration.money_method import state_method

pytestmark = pytest.mark.integration
IBERIA = "22222222-2222-4222-8222-222222222222"
SEGUROS = "496937e3-ea3c-4597-9066-c98cc1c2f742"


def _users(api):
    return _login(api, "analyst@iberia.demo", "Demo!analyst1"), _login(api, "approver@iberia.demo", "Demo!approve1")


def _state(api, maker, checker, pe, framework, values: dict, entity: str | None):
    for key, v in values.items():
        r = api.post("/v1/provided", headers=maker, json={"framework": framework, "datapoint_key": key, "value_num": v,
                                                          "reporting_period_end": pe.isoformat(), "reporting_entity_id": entity})
        assert r.status_code == 201, r.text
        d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker,
                     json={"decision": "approved", "reason": "per the undertaking's own figures"})
        assert d.status_code == 200, d.text


def _capital(api, maker, checker, pe):
    _state(api, maker, checker, pe, "insurer_solvency",
           {"eligible_own_funds_scr": 90_000_000, "scr_total": 60_000_000, "mcr_total": 20_000_000,
            "ri_quota_share_pct": 30, "ri_xol_attachment_eur": 2_000_000, "ri_xol_limit_eur": 10_000_000}, SEGUROS)


def _generate(api, maker, fw, disclosure_date):
    pf = api.get(f"/v1/filings/preflight?framework={fw}&entity_id={SEGUROS}", headers=maker)
    assert pf.status_code == 200, pf.text
    g = api.post("/v1/filings", headers=maker, json={"framework": fw, "confirm_token": pf.json()["confirm_token"],
                                                     "entity_id": SEGUROS, "disclosure_date": disclosure_date})
    assert g.status_code == 201, g.text
    fid = g.json()["filing_id"]
    return fid, json.loads(api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).content)["payload"]


def _findings(api, headers, fid):
    return {f["rule"]: f for f in api.get(f"/v1/filings/{fid}/validation", headers=headers).json()["findings"]}


def test_the_orsa_climate_analysis_from_the_attested_figures_to_the_submitted_report(api):
    maker, checker = _users(api)
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(api.s, IBERIA)
    state_method(api.s, IBERIA, pe)          # the insurer's stated method (E69)
    _capital(api, maker, checker, pe)

    live = api.get(f"/v1/insurance/documents/insurer_orsa_climate?entity_id={SEGUROS}", headers=maker)
    assert live.status_code == 200, live.text
    items = {i["id"]: i for i in live.json()["items"]}
    assert items["scenarios.below_2c"]["value"]["text"].startswith("Orderly transition (NGFS archetype), SSP1-2.6 — 1.8 °C")
    assert "SSP5-8.5 — 4.4 °C" in items["scenarios.above_2c"]["value"]["text"]
    impact = items["impact"]["value"]["table"]
    assert len(impact["rows"]) == 1 + 2 * 3                                     # today + 2 scenarios × 2030/2050/2100
    assert all(items[k]["status"] == "missing" for k in ("materiality", "sfcr.material", "impact.interval"))

    # the undertaking's answers: an interval over three years is refused (Art. 45a(3))
    put = lambda a: api.put("/v1/insurance/documents/insurer_orsa_climate/answers", headers=maker,   # noqa: E731
                            json={"answers": a, "entity_id": SEGUROS})
    assert put({"impact.interval": {"text": "5 years"}}).status_code == 422
    ok = put({"materiality": {"text": "Material: the modelled wildfire loss doubles under SSP5-8.5 by 2100."},
              "impact.interval": {"text": "1 year"}, "review": {"text": "Reviewed with the 2027 ORSA."},
              "review.performance": {"text": "Compared the 2026 projections with observed losses."},
              "sncu": {"ticked": False}, "sfcr": {"text": "See below."}, "sfcr.material": {"ticked": True},
              "sfcr.actions": {"text": "Wildfire accumulation limits in Valencia and inland Iberia."}})
    assert ok.status_code == 200 and not ok.json()["refused"], ok.text

    # made today (before 30 January 2027) nothing governs it; prepared for a conclusion on 31 March 2027, Art. 45a does
    fid0, p0 = _generate(api, maker, "insurer_orsa_climate", None)
    assert p0["_specs"]["sii_climate"]["version"] is None
    assert not _findings(api, maker, fid0)["specification"]["passed"]
    api.post(f"/v1/filings/{fid0}/withdraw", headers=maker, json={"reason": "made before the rules apply"})
    fid, payload = _generate(api, maker, "insurer_orsa_climate", "2027-03-31")
    assert payload["_specs"]["sii_climate"]["version"] == "dir_2025_2" and payload["_specs"]["sii_climate"]["disclosed_on"] == "2027-03-31"
    f = api.get(f"/v1/filings/{fid}", headers=maker).json()
    assert (f["disclosure_date"], f["due_date"]) == ("2027-03-31", "2027-04-14")          # Art. 312(1)(b): two weeks

    # the capital impact, worked from the attested figures: SCR ratio = own funds / (SCR + the net 1-in-200 change)
    doc = payload["document_report"]
    assert doc["reporting_entity_id"] == SEGUROS and doc["computed"]["capital"]["attested"]
    for r in doc["computed"]["runs"]:
        expect = round(100 * 90_000_000 / (60_000_000 + max(r["change_net_1_in_200_eur"], 0)), 1)
        assert r["scr_ratio_pct"] == pytest.approx(expect, abs=0.1)
        assert r["expected_annual_loss_eur"] >= doc["computed"]["today"]["expected_annual_loss_eur"] - 1   # warming never lowers
    assert doc["computed"]["treaty_basis"] == "attested"
    found = _findings(api, maker, fid)
    assert all(found[k]["passed"] for k in ("items_answered", "capital_attested", "treaty_attested", "interval_three_years"))

    form = api.get(f"/v1/filings/{fid}/form", headers=maker).json()
    sec = next(s for s in form["annex"]["sections"] if s["key"] == "insurer_orsa_climate_document")
    assert sec["kind"] == "document" and any(i["id"] == "impact" and i["status"] == "filled" for i in sec["items"])

    sr = api.post(f"/v1/filings/{fid}/submit-for-review", headers=maker)
    assert sr.status_code == 200, sr.text
    assert api.post(f"/v1/approvals/{sr.json()['approval_request_id']}/decide", headers=checker,
                    json={"decision": "approved", "reason": "ORSA climate analysis reviewed"}).status_code == 200
    assert api.post(f"/v1/filings/{fid}/attest", headers=checker, json={"statement": "The board approved the ORSA."}).status_code == 200
    assert api.post(f"/v1/filings/{fid}/submit", headers=maker, json={"submission_ref": "ORSA-2027"}).status_code == 200

    # the small and non-complex derogation (Art. 45a(5)): the scenario items are not required
    assert put({"sncu": {"ticked": True}}).status_code == 200
    waived = {i["id"]: i for i in api.get(f"/v1/insurance/documents/insurer_orsa_climate?entity_id={SEGUROS}",
                                          headers=maker).json()["items"]}
    assert waived["impact"]["status"] == "printed" and "Art. 45a(5)" in waived["impact"]["note"]


def test_the_recovery_plan_stress_against_the_attested_capital_and_indicators(api):
    maker, checker = _users(api)
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(api.s, IBERIA)
    state_method(api.s, IBERIA, pe)          # the insurer's stated method (E69)
    _capital(api, maker, checker, pe)
    low = api.post("/v1/provided", headers=maker, json={"framework": "insurer_recovery_stress", "datapoint_key": "scr_trigger_recovery_pct",
                                                        "value_num": 90, "reporting_period_end": pe.isoformat(), "reporting_entity_id": SEGUROS})
    assert low.status_code in (400, 422) and "between 100" in low.text      # below the SCR-breach level: refused
    _state(api, maker, checker, pe, "insurer_recovery_stress",
           {"scr_trigger_early_warning_pct": 160, "scr_trigger_recovery_pct": 130}, SEGUROS)
    assert api.put("/v1/insurance/documents/insurer_recovery_stress/answers", headers=maker, json={"entity_id": SEGUROS, "answers": {
        "stress.others": {"text": "Equity −35 %, spreads +250 bp, lapse shock, and their combination with the nat-cat event."},
        "indicators": {"text": "Capital, liquidity and profitability indicators, reviewed quarterly."},
        "indicators.triggers": {"text": "SCR ratio 160 % early warning, 130 % recovery action; liquidity coverage 120 %."},
        "indicators.monitoring": {"text": "Monthly SCR estimate to the risk committee."},
        "indicators.breach_action": {"text": "Capital injection from the parent and reinsurance purchase."}}}).status_code == 200

    fid, payload = _generate(api, maker, "insurer_recovery_stress", "2027-06-30")
    rec = payload["document_report"]["computed"]
    assert payload["_specs"]["irrd_recovery"]["version"] == "dir_2025_1"
    for e in rec["events"]:                                                    # worked by hand from the attested figures
        assert e["own_funds_after_eur"] == 90_000_000 - e["net_loss_eur"]
        ratio = round(100 * e["own_funds_after_eur"] / 60_000_000, 1)
        assert e["scr_ratio_after_pct"] == ratio and e["breaches_scr"] == (ratio < 100)
        assert set(e["triggers_crossed"]) == {n for n, lvl in (("SCR breach (Art. 5(8) minimum)", 100), ("Recovery-action level", 130),
                                                               ("Early-warning level", 160)) if ratio < lvl}
    assert rec["triggers"][0]["level_pct"] == 100.0 and {t["level_pct"] for t in rec["triggers"]} == {100.0, 130.0, 160.0}
    under = [e for e in rec["events"] if e["stress"].endswith("under warming")]
    today = [e for e in rec["events"] if e["stress"].endswith("today")]
    assert all(u["net_loss_eur"] >= t["net_loss_eur"] for u, t in zip(under, today))          # warming never lowers
    found = _findings(api, maker, fid)
    assert found["items_answered"]["passed"] and found["capital_attested"]["passed"] and found["treaty_attested"]["passed"]
