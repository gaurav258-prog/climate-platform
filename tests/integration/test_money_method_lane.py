"""The institution states its own methods and parameters (family 'method', per financial year, four eyes) — the only
way a method number reaches a monetary figure (E69). Through the HTTP API, one rolled-back transaction."""
from __future__ import annotations

from datetime import date

import pytest

from tests.integration.test_e2e_esrs_statement import TERRA, _approve, _period, _users

pytestmark = pytest.mark.integration
PE = "2025-12-31"


def _post(api, who, key, value, member=None):
    return api.post("/v1/provided", headers=who, json={"framework": "method", "datapoint_key": key, "value_num": value,
                                                       "reporting_period_end": PE, "breakdown_member": member})


def test_a_stated_method_parameter_is_what_the_engine_reads(api):
    from services.money.params import Method
    maker, checker = _users(api)
    _period(api, PE)
    cat = api.get("/v1/provided/catalog?framework=method", headers=maker).json()["datapoints"]
    dr = next(d for d in cat if d["key"] == "method.damage_ratio")
    assert dr["breakdown"] == "peril_band" and "flood/H" in dr["members"]

    m = Method(api.s, TERRA, date(2025, 12, 31))
    assert m.get("method.damage_ratio", "flood/H") is None and "method.damage_ratio (flood/H)" in m.gap_text()

    for body, why in ((("method.not_a_parameter", 0.1), "not a method parameter"),
                      (("method.damage_ratio", 0.2), "say which one"),
                      (("method.damage_ratio", 0.2, "flood/Z"), "is not a peril band"),
                      (("method.damage_ratio", 1.5, "flood/H"), "between 0 and 1"),
                      (("method.at_risk_level", 50, "flood/H"), "single figure")):
        r = _post(api, maker, *body)
        assert r.status_code == 400 and why in r.text, (body, r.text)

    r = _post(api, maker, "method.damage_ratio", 0.2, "flood/H")
    assert r.status_code == 201, r.text
    assert Method(api.s, TERRA, date(2025, 12, 31)).get("method.damage_ratio", "flood/H") is None   # not yet attested
    _approve(api, checker, r.json()["approval_request_id"])
    m = Method(api.s, TERRA, date(2025, 12, 31))
    assert m.get("method.damage_ratio", "flood/H") == 0.2 and m.gap_text() is None
    assert m.provenance("method.damage_ratio", "flood/H")["attested_by"] == "approver@terra.demo"
    assert Method(api.s, TERRA, date(2024, 12, 31)).get("method.damage_ratio", "flood/H") is None   # another year: not stated


def test_the_organisation_is_told_which_parameters_its_figures_still_need(api):
    """GET /v1/provided/method/needed runs the organisation's own figures and lists what they asked for and did not find
    — and nothing once the method is stated (E69)."""
    from tests.integration.conftest import login
    from tests.integration.money_method import state_method
    bank = "11111111-1111-4111-8111-111111111111"
    h = login(api, "admin@meridian.demo", "Demo!admin1")
    s = api.s
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(s, bank)
    already = {(r["datapoint_key"], r["breakdown_member"]) for r in api.get("/v1/provided?framework=method", headers=h).json()["provided"]}
    before = api.get("/v1/provided/method/needed", headers=h).json()
    assert before["period_end"] == pe.isoformat()
    if not already:
        assert {"key": "method.at_risk_level", "member": None} in before["needed"]
    state_method(s, bank, pe)
    after = api.get("/v1/provided/method/needed", headers=h).json()
    assert after["needed"] == [], after["needed"][:5]
    assert any(u["key"] == "method.at_risk_level" for u in after["used"])
