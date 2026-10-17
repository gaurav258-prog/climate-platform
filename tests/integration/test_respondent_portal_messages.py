"""The supervisory portal speaks customer words (UI standard, 2026-10-16): its explanations arrive as catalogue messages
(a label for the screen, a structured detail for the pop-up) and its refusals as catalogue codes — never a sentence
written in the router, never an internal key or an exception's own text. End to end through the real API, rolled back."""
from __future__ import annotations

import io

import pytest

from tests.integration.conftest import login

ADMIN = ("admin@meridian.demo", "Demo!admin1")          # Meridian Bank (demo), supervised by the EU Banking Supervisor (demo)


@pytest.fixture()
def me(api):
    api.h = login(api, *ADMIN)
    return api


def _refused(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    err = r.json()["error"]
    assert err["error"] == code and err["message"] and err["detail"]["what"]
    return err


def test_explanations_are_catalogue_messages(me):
    for path, code in (("/v1/me/supervisors", "supervision.respondent.access"),
                       ("/v1/me/supervisors/mandates", "supervision.respondent.mandates"),
                       ("/v1/me/supervisors/remittances", "supervision.respondent.shared_onward")):
        body = me.get(path, headers=me.h).json()
        assert "note" not in body and body["about"]["code"] == code and body["about"]["label"] and body["about"]["detail"]["what"]


def test_the_template_carries_its_basis_fields_and_the_threshold_message(me):
    sid = me.get("/v1/me/supervisors", headers=me.h).json()["supervisors"][0]["supervision_id"]
    spec = me.get(f"/v1/me/supervisors/{sid}/submission-spec", headers=me.h).json()
    assert spec["available"] and {"scenario", "horizon"} <= {b["id"] for b in spec["basis_fields"]}
    want = "supervision.respondent.level_stated" if spec["at_risk_level"] is not None else "supervision.respondent.level_not_stated"
    assert spec["level_message"]["code"] == want and "note" not in spec


def test_refusals_are_catalogue_codes_in_customer_words(me):
    req = me.get("/v1/me/supervisors/requests", headers=me.h).json()["requests"][0]["request_id"]
    _refused(me.post(f"/v1/me/supervisors/requests/{req}/messages", headers=me.h, json={}), 422, "supervision.respondent.empty_reply")
    err = _refused(me.put("/v1/me/supervisors/regulatory-attributes", headers=me.h, json={"attributes": {"sector": "bank"}}),
                   422, "supervision.respondent.attribute_not_yours")
    assert "Sector (activity type)" in err["detail"]["what"] and "sector " not in err["detail"]["what"]   # its label, not its key
    _refused(me.get("/v1/me/supervisors/requests/00000000-0000-4000-8000-000000000000", headers=me.h), 404, "error.not_found")


def test_a_file_that_cannot_be_read_or_a_basis_out_of_range_is_refused_in_words(me):
    sid = me.get("/v1/me/supervisors", headers=me.h).json()["supervisors"][0]["supervision_id"]
    files = {"file": ("book.xlsx", io.BytesIO(b"not a spreadsheet"), "application/octet-stream")}
    _refused(me.post(f"/v1/me/supervisors/{sid}/submissions/validate", headers=me.h, files=files), 400, "supervision.respondent.unreadable_file")
    csv = b"Geography,Sector,Gross carrying amount,of which sensitive to physical risk\nDE,A,100,50\n"
    form = {"mapping": "{}", "period_label": "FY2025", "basis": '{"at_risk_level": 150}'}
    r = me.post(f"/v1/me/supervisors/{sid}/submissions", headers=me.h, data=form, files={"file": ("t.csv", io.BytesIO(csv), "text/csv")})
    _refused(r, 422, "supervision.respondent.basis_invalid")


def test_calendar_reports_carry_their_facts_as_fields(me):
    reports = [e for e in me.get("/v1/reg-tasks/calendar", headers=me.h).json()["events"] if e["kind"] == "obligation"]
    assert reports and all({"period", "frequency", "entity", "set_by"} <= set(e) for e in reports)
    assert all(e["period"] and e["frequency"] for e in reports)
