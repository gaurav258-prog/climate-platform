"""End to end, through the HTTP API: the insurer foundation the Solvency II, ORSA and recovery reports stand on.

  a Statement of Values upload (three properties on scored locations) → every insured peril priced on its own, the
  policy the sum of its perils, nothing priced for a peril the property cover does not indemnify → own funds, SCR,
  MCR and the reinsurance treaty submitted by one person and attested by another (not before) → the book nets its
  losses with the attested treaty, not the illustrative one → the Solvency II nat-cat and climate filings freeze,
  their frozen figures tie to the engine at the filing's basis, and export → another organisation sees none of it.

The API runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import csv
import io
import json

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
IBERIA = "22222222-2222-4222-8222-222222222222"


def _csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def test_insurer_foundation_from_the_statement_of_values_to_the_filings(api):
    maker = _login(api, "analyst@iberia.demo", "Demo!analyst1")
    checker = _login(api, "approver@iberia.demo", "Demo!approve1")
    other = _login(api, "admin@stellar.demo", "Demo!admin1")
    s = api.s
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, IBERIA)

    # 1 · three properties on locations the engine has scored (the coordinates of existing Iberia policies)
    spots = s.execute(text("""SELECT DISTINCT ON (region) latitude, longitude, region, country FROM portfolio_entities
                              WHERE org_id = CAST(:o AS uuid) AND vertical = 'insurance' AND h3_cell IS NOT NULL
                              ORDER BY region, entity_name LIMIT 3"""), {"o": IBERIA}).mappings().all()
    rows = [{"policy_name": f"E2E property {i}", "latitude": r["latitude"], "longitude": r["longitude"], "region": r["region"],
             "country": r["country"], "building_value_eur": 4_000_000 + i * 1_000_000, "contents_value_eur": 500_000,
             "construction_type": "joisted_masonry", "year_built": 1985, "number_of_stories": 3, "deductible_pct": 0.01}
            for i, r in enumerate(spots, 1)]
    up = api.post("/v1/insurance/policies/upload", headers=maker, files={"file": ("sov.csv", _csv(rows), "text/csv")}, data={"currency": "EUR", "book_date": pe.isoformat()})
    assert up.status_code == 200, up.text

    # 2 · every insured peril priced on its own; the policy is their sum; no peril the cover does not indemnify
    from ml.scoring.insurance_pricing import insured_peril
    book = api.get("/v1/insurance/portfolio?scenario=hot_house_3_5c&horizon=2050", headers=maker).json()
    mine = [p for p in book["policies"] if p["policy_name"].startswith("E2E property")]
    assert len(mine) == 3
    for p in mine:
        pr = p["pricing"]
        assert pr and pr["perils"], p["policy_name"]
        assert all(insured_peril(c["hazard"]) or c["hazard"] in ("subsidence", "landslide") for c in pr["perils"])
        assert not {c["hazard"] for c in pr["perils"]} & {"drought", "heat_chronic", "heat_acute", "pollution"}
        assert pr["expected_annual_loss_eur"] == pytest.approx(sum(c["expected_annual_loss_eur"] for c in pr["perils"]), abs=0.05)
        assert p["sum_insured_eur"] == pytest.approx(next(r for r in rows if r["policy_name"] == p["policy_name"])["building_value_eur"] + 500_000)

    # 3 · the capital position and the treaty: stated by one person, attested by another — not used before
    from api.routers.insurance import build_disclosure_snapshot
    before = build_disclosure_snapshot(s, IBERIA, "baseline", "current")["reinsurance"]
    assert before["program_basis"] == "illustrative_standard"
    stated = {"eligible_own_funds_scr": 180_000_000, "scr_total": 120_000_000, "mcr_total": 45_000_000,
              "ri_quota_share_pct": 30, "ri_xol_attachment_eur": 8_000_000, "ri_xol_limit_eur": 40_000_000}
    requests = []
    for key, v in stated.items():
        r = api.post("/v1/provided", headers=maker, json={"framework": "insurer_solvency", "datapoint_key": key,
                                                          "value_num": v, "reporting_period_end": pe.isoformat()})
        assert r.status_code == 201, r.text
        requests.append(r.json()["approval_request_id"])
    assert build_disclosure_snapshot(s, IBERIA, "baseline", "current")["reinsurance"]["program_basis"] == "illustrative_standard"
    own = api.post(f"/v1/approvals/{requests[0]}/decide", headers=maker, json={"decision": "approved"})
    assert own.status_code in (403, 422)                                   # the maker cannot attest their own value
    for rid in requests:
        ok = api.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": "per S.23.01 and treaties"})
        assert ok.status_code == 200, ok.text
    from services.insurer_capital import position, programme
    cap = position(s, IBERIA, pe)
    assert (cap["eligible_own_funds_scr"], cap["scr_total"], cap["scr_ratio_pct"]) == (180_000_000, 120_000_000, 150.0)
    prog, basis = programme(s, IBERIA, pe)
    assert basis == "attested" and prog == {"quota_share_pct": 30.0, "xol_attachment_eur": 8_000_000.0, "xol_limit_eur": 40_000_000.0}

    # 4 · the book nets with the attested treaty
    snap = build_disclosure_snapshot(s, IBERIA, "baseline", "current")
    net = snap["reinsurance"]["net"]
    assert snap["reinsurance"]["program_basis"] == "attested" and net["quota_share_pct"] == 30.0
    gross_oep = snap["rollup"]["catastrophe"]["oep_eur"]["rp_200"]
    assert net["net_oep_eur"]["rp_200"] <= 0.7 * gross_oep + 1                  # QS 30 %, then the cat layer on top

    # 5 · the Solvency II nat-cat and climate filings freeze, tie to the engine at their basis, and export
    from services.governance.reporting_settings import get_settings
    basis_settings = get_settings(s, IBERIA)
    engine = build_disclosure_snapshot(s, IBERIA, basis_settings["scenario"], basis_settings["horizon"])
    for fw in ("insurer_solvency", "insurer_climate"):
        # a live draft of the demo (from an earlier walkthrough) is withdrawn first, through the governed withdraw
        for (live,) in s.execute(text("""SELECT filing_id::text FROM regulatory_filing WHERE org_id = CAST(:o AS uuid)
                                         AND framework = :f AND period_end = :pe AND entity_id IS NULL AND status = 'draft'"""),
                                 {"o": IBERIA, "f": fw, "pe": pe}).all():
            assert api.post(f"/v1/filings/{live}/withdraw", headers=maker,
                            json={"reason": "superseded by the end-to-end test filing"}).status_code == 200
        pf = api.get(f"/v1/filings/preflight?framework={fw}", headers=maker).json()
        g = api.post("/v1/filings", headers=maker, json={"framework": fw, "confirm_token": pf["confirm_token"]})
        assert g.status_code == 201, g.text
        fid = g.json()["filing_id"]
        payload = json.loads(api.get(f"/v1/filings/{fid}/export?format=json", headers=maker).content)["payload"]
        # the frozen book is the engine's at the filing's basis: same policies, same expected loss, same 1-in-200
        roll = payload["rollup"]
        assert roll["n_policies"] == engine["rollup"]["n_policies"] and roll["total_sum_insured_eur"] == engine["rollup"]["total_sum_insured_eur"]
        assert roll["total_expected_annual_loss_eur"] == engine["rollup"]["total_expected_annual_loss_eur"], fw
        assert roll["catastrophe"]["aep_eur"]["rp_200"] == engine["rollup"]["catastrophe"]["aep_eur"]["rp_200"], fw
        if fw == "insurer_solvency":
            assert payload["s2601"]["natcat_scr"] and payload["s2601"]["standard_formula_natcat"]
            assert {x["key"] for x in payload["_provided_attested"]} >= {f"provided.{k}" for k in stated}
        assert api.get(f"/v1/filings/{fid}/export?format=xlsx", headers=maker).status_code == 200
        assert api.get(f"/v1/filings/{fid}/form", headers=maker).status_code == 200

    # 6 · another organisation sees none of it
    pid = s.execute(text("""SELECT entity_id::text FROM portfolio_entities WHERE org_id = CAST(:o AS uuid)
                            AND entity_name = 'E2E property 1'"""), {"o": IBERIA}).scalar()
    assert api.get(f"/v1/insurance/policy/{pid}", headers=other).status_code == 404
    assert not [x for x in api.get("/v1/provided?framework=insurer_solvency", headers=other).json()["provided"]
                if x.get("datapoint_key") in stated]
