"""Losses into decisions (the product owner's decisions of 2026-10-22). Rolled back throughout.

  indicator   the book's tested yearly loss is the sum of its tested figures, at the stated flood lead; flood figures
              waiting for that lead hold the indicator back (a total without them would understate the book)
  signal      the assets whose tested yearly loss reaches the share of their value the institution states; not stated,
              no signal and the named gap
  decide      a loss decision is on today's climate, kept apart from crossings, its standing call the latest by sequence
  watch       a loss watch is re-checked on the asset's tested-loss share and escalates when it has risen"""
from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy import text

import services.intelligence.decision_watch as W
import services.intelligence.forward_decisions as D
from services.loss import curves, engine, signals
from services.money.params import Method
from tests.integration.test_loss_engine import LAT, _asset, _flood_samples, _storm_samples

pytestmark = pytest.mark.integration
ORG = "0bbe0bbe-0000-4000-8000-0000005161a1"
PERIOD = date(2026, 12, 31)


def _reit(s, monkeypatch, elections: dict) -> str:
    """A REIT whose book holds only the test assets, every figure's curve treated as tested (its standing is the curve
    test's, which these tests do not depend on)."""
    s.execute(text("INSERT INTO organizations (org_id, name, type, country) VALUES (:o, 'signal test', 'reit', 'US')"),
              {"o": ORG})
    s.execute(text("""INSERT INTO org_calc_settings (org_id, interpretation, updated_at)
                      VALUES (CAST(:o AS uuid), CAST(:i AS jsonb), now())"""), {"o": ORG, "i": json.dumps(elections)})
    s.execute(text("""INSERT INTO approval_policy (org_id, action_key, requires_approval) VALUES (:o, 'risk.decision', FALSE)
                      ON CONFLICT (org_id, action_key) WHERE org_id IS NOT NULL DO UPDATE SET requires_approval = FALSE"""),
              {"o": ORG})
    monkeypatch.setattr(engine, "standing", lambda f, c, cv=None: "published")
    return ORG


def _storm_book(s, monkeypatch) -> tuple[str, str]:
    """Two US homes on a cyclone coast: the second sees stronger winds, so a larger share of its value is lost."""
    if "eberenz_2021_rmsf" not in curves.families():
        pytest.skip("the cyclone family is not built on this machine")
    org = _reit(s, monkeypatch, {"loss_curve_family_storm": "eberenz_2021_rmsf"})
    a = _asset(s, org)
    _storm_samples(s, at_100=40.0)
    b = _asset(s, org, lat=LAT + 0.01)
    _storm_samples(s, lat=LAT + 0.01, at_100=55.0)
    engine.run(s, org, "realestate")
    return a, b


def _actor(s) -> str:
    return s.execute(text("SELECT user_id::text FROM users ORDER BY created_at, user_id LIMIT 1")).scalar()


def test_the_indicator_is_the_sum_of_the_tested_figures(session_rolled_back, monkeypatch):
    from services.governance.kri import FLOW_KRIS
    from services.governance.kri_loss import KEY, tested_loss_kpi
    s = session_rolled_back
    _storm_book(s, monkeypatch)
    c = signals.carried(s, ORG)
    assert c["book"] == "realestate" and len(c["figures"]) == 2
    assert all(f["share"] == pytest.approx(f["loss_eur"] / f["exposed_value_eur"]) for f in c["figures"])
    k = tested_loss_kpi(s, ORG)
    assert k["key"] == KEY and KEY in FLOW_KRIS and k["missing"] is None
    assert k["value"] == round(sum(f["loss_eur"] for f in c["figures"]))
    assert {f["key"]: f["value"] for f in k["facts"]}["tested_figures"] == 2


def test_no_run_and_no_tested_figure_are_named(session_rolled_back, monkeypatch):
    s = session_rolled_back
    _reit(s, monkeypatch, {})
    assert signals.yearly_loss(s, ORG)["why"] == "loss.signal.no_run"
    monkeypatch.setattr(engine, "standing", lambda f, c, cv=None: "held")
    _asset(s, ORG)
    _storm_samples(s)
    engine.run(s, ORG, "realestate")
    y = signals.yearly_loss(s, ORG)
    assert y["value"] is None and y["why"] == "loss.signal.no_tested_figure"


def test_tested_flood_figures_wait_for_the_stated_lead(session_rolled_back, monkeypatch):
    s = session_rolled_back
    if "jrc_huizinga_2017" not in curves.families():
        pytest.skip("the JRC family is not built on this machine")
    _reit(s, monkeypatch, {"loss_curve_family_flood": "jrc_huizinga_2017"})
    _asset(s, ORG)
    _flood_samples(s)
    engine.run(s, ORG, "realestate")
    y = signals.yearly_loss(s, ORG)
    assert y["withheld"][signals.FLOOD_LEAD_NOT_STATED] == 1 and y["value"] is None
    assert y["why"] == "loss.signal.flood_lead_not_stated"
    s.execute(text("""UPDATE org_calc_settings SET interpretation = interpretation || '{"loss_flood_headline": "undefended"}'
                      WHERE org_id = CAST(:o AS uuid)"""), {"o": ORG})
    y = signals.yearly_loss(s, ORG)
    assert y["why"] is None and y["figures"][0]["basis"] in ("undefended",)


def test_the_signal_is_the_stated_share_and_nothing_without_it(session_rolled_back, monkeypatch):
    s = session_rolled_back
    a, b = _storm_book(s, monkeypatch)
    share = {f["asset_id"]: f["share"] for f in signals.carried(s, ORG)["figures"]}
    assert share[b] > share[a] > 0
    none = signals.signals(s, ORG, Method.of({}, PERIOD))
    assert none["level"] is None and none["signals"] == [] and none["gap"] == "not stated: method.loss_signal_share"
    level = (share[a] + share[b]) / 2
    out = D.loss_signals(s, ORG, Method.of({("method.loss_signal_share", None): level}, PERIOD))
    assert [x["entity_id"] for x in out["signals"]] == [b] and out["signals"][0]["decision"] is None
    out = signals.signals(s, ORG, Method.of({("method.loss_signal_share", None): share[a]}, PERIOD))
    assert [x["entity_id"] for x in out["signals"]] == [b, a]                  # at the level counts; largest loss first


def test_a_loss_decision_is_on_todays_climate_and_apart_from_crossings(session_rolled_back, monkeypatch):
    s = session_rolled_back
    a, b = _storm_book(s, monkeypatch)
    actor = _actor(s)
    level = Method.of({("method.loss_signal_share", None): 0.0}, PERIOD)
    r = D.decide(s, ORG, actor, entity_id=b, entity_name="b", scenario="hot_house_3_5c", horizon="2100",
                 action="insure", rationale="t", signal="loss")
    row = s.execute(text("SELECT signal, scenario, horizon, status FROM risk_decision WHERE decision_id = CAST(:d AS uuid)"),
                    {"d": r["decision_id"]}).mappings().one()
    assert dict(row) == {"signal": "loss", "scenario": "baseline", "horizon": "current", "status": "approved"}
    got = {x["entity_id"]: x["decision"] for x in D.loss_signals(s, ORG, level)["signals"]}
    assert got[b]["action"] == "insure" and got[a] is None
    assert D._live_decisions(s, ORG, "baseline", "current") == {}             # a crossing never reads a loss decision
    # two calls in one transaction share decided_at: the standing call is the later one, by sequence
    D.decide(s, ORG, actor, entity_id=b, entity_name="b", scenario=None, horizon=None, action="dispose",
             rationale="t", signal="loss")
    assert D._live_decisions(s, ORG, "baseline", "current", signal="loss")[b]["action"] == "dispose"
    assert D.decisions_log(s, ORG)[0]["action"] == "dispose" and D.decisions_log(s, ORG)[0]["signal"] == "loss"


def test_a_loss_watch_is_rechecked_on_the_tested_loss_share(session_rolled_back, monkeypatch):
    s = session_rolled_back
    _a, b = _storm_book(s, monkeypatch)
    actor = _actor(s)
    D.set_playbook(s, ORG, actor, "monitor", {"watchlist": True, "due_days": 90})
    D.decide(s, ORG, actor, entity_id=b, entity_name="b", scenario=None, horizon=None, action="monitor",
             rationale="t", signal="loss")
    w = next(x for x in W.watchlist(s, ORG) if x["entity_name"] == "b")
    assert w["signal"] == "loss" and w["baseline_share"] == pytest.approx(signals.asset_share(s, ORG, b))
    assert w["baseline_score"] is None
    assert W.recheck_watchlist(s, ORG) == []                                  # unchanged: stays watching
    s.execute(text("UPDATE decision_watchlist SET baseline_share = baseline_share / 2 WHERE org_id = CAST(:o AS uuid)"),
              {"o": ORG})
    esc = W.recheck_watchlist(s, ORG)
    assert [(e["signal"], e["entity_name"]) for e in esc] == [("loss", "b")] and esc[0]["share"] > esc[0]["baseline_share"]
    assert next(x for x in W.watchlist(s, ORG) if x["entity_name"] == "b")["status"] == "escalated"


def test_the_route_answers_in_customer_words(session_rolled_back, monkeypatch):
    """GET /v1/decisions/loss-signals: the signals with their perils named, the reason a figure is missing as a
    catalogue message, the organisation's 4-eyes rule — for a book with figures and gaps alike."""
    import api.routers.decisions as R
    s = session_rolled_back
    a, b = _storm_book(s, monkeypatch)
    _asset(s, ORG, building=None, lat=LAT + 0.02)                 # a gap with its own values (no building value)
    _storm_samples(s, lat=LAT + 0.02)
    engine.run(s, ORG, "realestate")
    share = {f["asset_id"]: f["share"] for f in signals.carried(s, ORG)["figures"]}
    monkeypatch.setattr("services.money.params.for_org",
                        lambda *_a, **_k: Method.of({("method.loss_signal_share", None): share[a]}, PERIOD))
    out = R.loss_signals(s, ctx={"org": {"org_id": ORG, "type": "reit"}, "user": {"id": _actor(s)}})
    assert out["n"] == 2 and out["notice"] is None and out["policy"]["requires_approval"] is False
    assert {f["peril_name"] for x in out["signals"] for f in x["figures"]} == {"tropical cyclone"}
    assert out["gaps"] and out["withheld"]["gap"] >= 1
    monkeypatch.setattr(engine, "standing", lambda f, c, cv=None: "held")
    engine.run(s, ORG, "realestate")
    out = R.loss_signals(s, ctx={"org": {"org_id": ORG, "type": "reit"}, "user": {"id": _actor(s)}})
    assert out["n"] == 0 and out["notice"]["code"] == "loss.signal.no_tested_figure" and out["notice"]["label"]
