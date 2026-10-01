"""End to end, through the HTTP API: the supervisor's at-risk figures rest on stated levels, never on a band of the
platform's choosing (E69).

  the authority's own stated level — the one yardstick of its population views: without it the peer benchmark's
  at-risk metrics and the lens are named gaps; with it they are computed at that level;
  the entity's level — the one its template was computed on: the plausibility band reads the submitted share and the
  geography's reference at that level, and says where the level came from.

The API runs in one rolled-back transaction: nothing is left behind.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login
from tests.integration.money_method import state_method

pytestmark = pytest.mark.integration
SUPERVISOR = "88888888-8888-4888-8888-888888888888"      # EU Banking Supervisor (demo)
MERIDIAN = "11111111-1111-4111-8111-111111111111"        # a supervised bank with a submitted Template 5


def _period_end(s, org_id):
    from services.governance.filings import reporting_period_end
    return reporting_period_end(s, org_id)


def _money_metric(bench: dict) -> dict:
    bank = bench["sectors"]["bank"]
    return next(m for m in bank["metrics"] if m["id"] == "money_at_high_risk_eur")


def test_the_authoritys_views_are_a_gap_until_it_states_its_level_then_read_at_it(api):
    h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    s = api.s
    before = api.get("/v1/supervisor/benchmark", headers=h).json()
    assert before["at_risk_level"] is None and "method.at_risk_level" in before["gap"]
    assert all(e["value"] is None for e in _money_metric(before)["entities"])
    lens = api.get(f"/v1/supervisor/entity/{MERIDIAN}/lens", headers=h).json()
    assert lens["status"] == "gap" and "method.at_risk_level" in lens["message"]

    state_method(s, SUPERVISOR, _period_end(s, SUPERVISOR), {("method.at_risk_level", None): 50.0})
    at_50 = api.get("/v1/supervisor/benchmark", headers=h).json()
    assert at_50["at_risk_level"] == 50.0 and "gap" not in at_50
    vals_50 = {e["org_id"]: e["value"] for e in _money_metric(at_50)["entities"]}
    assert any(v for v in vals_50.values())
    analytics = api.get("/v1/supervisor/analytics", headers=h).json()
    assert analytics["at_risk_level"] == 50.0 and analytics["scenario_shift"]["at_risk_level"] == 50.0
    lens = api.get(f"/v1/supervisor/entity/{MERIDIAN}/lens", headers=h).json()
    assert lens["status"] in ("ok", "no_shadow_book") and lens["at_risk_level"]["regulator"] == 50.0
    # the gap split still adds up exactly
    t = lens["totals"]
    assert t["scope"] + t["coverage"] + t["basis"] + t["scoring"] + t["unmatched"] == pytest.approx(lens["total_gap"], abs=len(lens["cells"]) + 1)


def test_a_higher_stated_level_never_raises_the_money_at_risk(api):
    h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    s = api.s
    pe = _period_end(s, SUPERVISOR)
    state_method(s, SUPERVISOR, pe, {("method.at_risk_level", None): 50.0})
    low = {e["org_id"]: e["value"] for e in _money_metric(api.get("/v1/supervisor/benchmark", headers=h).json())["entities"]}
    s.execute(text(
        "UPDATE provided_datapoint SET value_num = 75 WHERE org_id = CAST(:o AS uuid) AND framework = 'method' "
        "AND datapoint_key = 'method.at_risk_level'"), {"o": SUPERVISOR})
    high = {e["org_id"]: e["value"] for e in _money_metric(api.get("/v1/supervisor/benchmark", headers=h).json())["entities"]}
    assert all(high[k] <= low[k] for k in low if low[k] is not None)


def test_the_plausibility_band_reads_the_template_at_the_entitys_own_level(api):
    h = _login(api, "admin@supervisor.demo", "Demo!admin1")
    s = api.s
    r = api.get(f"/v1/supervisor/entity/{MERIDIAN}/plausibility", headers=h)
    if r.status_code == 404:
        pytest.skip("no submitted template for the demo bank")
    body = r.json()
    if body.get("status") == "gap":                               # the submission carries no level, nor does the bank's method
        assert "at-risk level" in body["gap"]
        state_method(s, MERIDIAN, _period_end(s, MERIDIAN), {("method.at_risk_level", None): 60.0})
        body = api.get(f"/v1/supervisor/entity/{MERIDIAN}/plausibility", headers=h).json()
        assert body["at_risk_level"] == 60.0 and body["at_risk_level_from"] == "entity_method"
    assert body["at_risk_level"] is not None and "at or above the entity's at-risk level" in body["rule"]
    banded = [row["band"] for row in body["rows"] if row["band"]]
    assert all(b["at_risk_level"] == body["at_risk_level"] for b in banded)
