"""End to end, through the HTTP API: the supervisor's intake speaks in catalogue messages (UI standard, 2026-10-16).
Every refusal is a code with its customer words and pop-up detail; every save answers with a message; a row problem is
a code counted over every row. The API runs in one rolled-back transaction, and no real scoring job is queued."""
from __future__ import annotations

import json
import uuid

import pytest

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
MERIDIAN = "11111111-1111-4111-8111-111111111111"        # a supervised bank of the EU Banking Supervisor (demo)
BASE = f"/v1/supervisor/intake/{MERIDIAN}"
GRANULAR = (b"Loan ref,Debtor,NACE,Outstanding amount,Final maturity,Protection country,Protection NUTS3\n"
            b"L1,Alpha SA,F,1250000,2031-06-30,ES,ES511\nL2,Beta SL,C,abc,2030-01-01,ES,ES511\n"
            b"L3,Gamma SA,,500000,2029-12-31,PT,PT170\nL4,Delta,G,1.000.000,2032-03-31,PT,\n")
TEMPLATE = b"Geography,Sector,Gross carrying amount,of which sensitive\nES,C,1000,400\nPT,F,500,100\n"


def _post(api, h, path, raw, name, **form):
    return api.post(path, headers=h, files={"file": (name, raw, "text/csv")}, data=form)


def _error(r) -> dict:
    e = r.json()["error"]
    assert e["message"] and e["detail"]["what"], e
    return e


def test_a_checked_file_names_what_blocks_it_and_counts_problems_by_code(api):
    h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    rep = _post(api, h, f"{BASE}/granular/validate", GRANULAR, "extract.csv").json()
    assert rep["mapping"]["instrument_id"] is None and rep["missing_required"] == ["instrument_id"]
    msg = rep["status_message"]
    assert msg["code"] == "supervision.intake.unmatched_fields" and "Instrument id" in msg["detail"]["what"]
    r = _post(api, h, f"{BASE}/granular", GRANULAR, "extract.csv", mapping=json.dumps(rep["mapping"]), period_label="FY2025")
    assert r.status_code == 422 and _error(r)["error"] == "supervision.intake.unmatched_fields"

    m = {**rep["mapping"], "instrument_id": "Loan ref"}
    rep = _post(api, h, f"{BASE}/granular/validate", GRANULAR, "extract.csv", mapping=json.dumps(m)).json()
    assert rep["ok"] and rep["status_message"] is None and (rep["n_valid"], rep["n_error"]) == (2, 2)
    kinds = {(t["code"], t["field"]): t["count"] for t in rep["problem_types"]}
    assert kinds == {("supervision.intake.row.not_a_number", "outstanding_eur"): 1, ("supervision.intake.row.missing", "nace_section"): 1}

    r = _post(api, h, f"{BASE}/granular", GRANULAR, "extract.csv", mapping=json.dumps(m), period_label="2025-Q3")
    assert r.status_code == 422 and _error(r)["error"] == "supervision.intake.invalid_period"
    r = _post(api, h, f"{BASE}/granular", GRANULAR, "extract.csv", mapping=json.dumps(m), period_label="2025")
    saved = r.json()
    assert r.status_code == 200 and saved["period_label"] == "FY2025"
    assert saved["message"]["code"] == "supervision.intake.data_imported" and saved["message"]["label"] == "Granular data imported for FY2025"
    status = api.get(BASE, headers=h).json()
    assert status["entity_name"] and status["shadow_book"]["n_rows"] == 2

    run = api.post(f"{BASE}/projections/run", headers=h).json()
    assert run["message"]["code"] == "supervision.intake.projections_started"


def test_a_template_saves_with_a_stated_basis_the_lens_can_rebuild_at(api):
    h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    rep = _post(api, h, f"{BASE}/submission/validate", TEMPLATE, "t5.csv").json()
    assert rep["ok"]
    m = json.dumps(rep["mapping"])
    r = _post(api, h, f"{BASE}/submission", TEMPLATE, "t5.csv", mapping=m, period_label="FY2023",
              basis=json.dumps({"scenario": "Disorderly 2°C"}))
    assert r.status_code == 422 and _error(r)["error"] == "supervision.intake.invalid_basis"
    r = _post(api, h, f"{BASE}/submission", TEMPLATE, "t5.csv", mapping=m, period_label="FY2023",
              basis=json.dumps({"scenario": "disorderly_2c", "horizon": "2030", "at_risk_level": "60"}))
    assert r.status_code == 200 and r.json()["message"]["label"] == "Template saved for FY2023"
    on_file = next(s for s in api.get(BASE, headers=h).json()["submissions"] if s["period_label"] == "FY2023" and s["framework"] != "granular")
    assert on_file["basis"] == {"scenario": "disorderly_2c", "horizon": "2030", "at_risk_level": 60.0} and on_file["n_cells"] == 2


def test_an_entity_outside_the_population_is_a_catalogue_refusal(api):
    h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    r = api.get(f"/v1/supervisor/intake/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404 and _error(r)["error"] == "supervision.intake.not_in_population"
    r = _post(api, h, f"{BASE}/other/validate", TEMPLATE, "t5.csv")
    assert r.status_code == 404 and _error(r)["error"] == "supervision.intake.unknown_file"
