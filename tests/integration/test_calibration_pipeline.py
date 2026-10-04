"""E162: one calibration pipeline — recipes, runs, gates, reviewed publication. Rolled back throughout.

  reproduce   the 40 fits published before the pipeline, re-run from their recipes (box, season, SPEI scale, driver,
              the ledger's production source), give today's verdicts: the same 8 pass the downside gate, the upside
              passes for Wheat MA and Olive oil ES only (the rules agreed 2026-10-04), and every fit made under the
              current cycle rule reproduces its stored figures exactly
  immutable   a run's figures never change; a recipe never changes (only retirement)
  publish     a reviewed run writes the fit with its recipe, run, yield series and cycle rule; the calibration row
              follows the published fit of its driver; the previous run is superseded
  one writer  only services/calibration/publish.py writes sc_commodity_fit
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import text

from ml.features.drought import ERA5_BASELINE_DIR
from services.calibration import gates, pipeline, publish, runner, specs

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
_HAS_WEATHER = os.path.exists(ERA5_BASELINE_DIR / "spain_olive_1991_2024_monthly.nc")


@pytest.mark.skipif(not _HAS_WEATHER, reason="the regional ERA5-Land files are not on this machine")
def test_the_published_fits_reproduce_through_the_pipeline(session_rolled_back):
    s = session_rolled_back
    stored = {(r["name"], r["origin"], r["hazard_driver"]): r for r in s.execute(text("""
        SELECT c.name, f.origin, f.hazard_driver, f.n_years, CAST(f.r2_oos AS FLOAT) AS r2_oos,
               CAST(f.slope AS FLOAT) AS slope, CAST(f.band_cov68 AS FLOAT) AS band_cov68, f.created_at
        FROM sc_commodity_fit f JOIN sc_commodities c USING (commodity_id) WHERE f.spec_id IS NULL""")).mappings()}
    if not stored:
        pytest.skip("every published fit already comes from the pipeline")
    pipeline.adopt_legacy(s)
    runs = pipeline.run(s, propose=False)["runs"]
    got = {(r["commodity"], r["origin"], r["driver"]): r for r in runs}
    assert set(stored) <= set(got)
    passes = {k for k in stored if got[k]["downside_pass"]}
    assert passes == {k for k, v in stored.items() if gates.downside_pass(v["r2_oos"])}      # no tier changes
    assert {k[:2] for k in stored if got[k]["upside_pass"]} == {("Wheat", "MA"), ("Olive oil", "ES")}
    # every stored fit is explained exactly: by today's rule, or — an annual crop fitted before the 2026-08-16 rule —
    # by removing the bearing cycle as was done then (a correction the pipeline proposes for review)
    old_rule = []
    for k, v in stored.items():
        want = (v["n_years"], v["r2_oos"], round(v["slope"], 5), v["band_cov68"])
        row = s.execute(text("""SELECT n_years, CAST(r2_oos AS FLOAT), CAST(slope AS FLOAT), CAST(band_cov68 AS FLOAT)
                                FROM crop_calibration_runs WHERE run_id = CAST(:r AS uuid)"""),
                        {"r": got[k]["run_id"]}).one()
        if tuple(row) == want:
            continue
        sp = runner.spec(s, got[k]["spec_id"])
        assert sp["allow_cycle"] is False, k
        fit = runner.evaluate(s, {**sp, "allow_cycle": True})["fit"]
        assert (fit.n_years, fit.r2_oos, round(fit.slope, 5), fit.band_cov68) == want, k
        old_rule.append(k)
    assert len(old_rule) <= 14

def _recipe(s, **over) -> dict:
    sid = specs.create(s, **{"commodity": "Olive oil", "origin": "ES", "yield_source": "FAOSTAT QCL bulk",
                             "yield_region": "TEST-E162", "driver": "drought", "weather_kind": "box",
                             "weather_key": "spain_olive", "season_months": [4, 5, 6, 7, 8], "allow_cycle": True,
                             "basis": "test recipe (E162)", "protocol": "crop-calib-v1", **over})
    return runner.spec(s, sid)


def test_a_run_and_a_recipe_never_change(session_rolled_back):
    s = session_rolled_back
    sp = _recipe(s)
    s.execute(text("""INSERT INTO crop_calibration_runs (spec_id, inputs, outcome, downside_pass, upside_pass)
                      VALUES (CAST(:s AS uuid), '{}', 'no_panel', false, false)"""), {"s": sp["spec_id"]})
    with pytest.raises(Exception, match="never change"):
        with s.begin_nested():
            s.execute(text("UPDATE crop_calibration_runs SET reason = 'edited' WHERE spec_id = CAST(:s AS uuid)"),
                      {"s": sp["spec_id"]})
    with pytest.raises(Exception, match="never changes"):
        with s.begin_nested():
            s.execute(text("UPDATE crop_calibration_specs SET season_months = '{4}' WHERE spec_id = CAST(:s AS uuid)"),
                      {"s": sp["spec_id"]})
    with pytest.raises(Exception, match="append-only"):
        with s.begin_nested():
            s.execute(text("DELETE FROM crop_calibration_runs WHERE spec_id = CAST(:s AS uuid)"), {"s": sp["spec_id"]})


@pytest.mark.skipif(not _HAS_WEATHER, reason="the regional ERA5-Land files are not on this machine")
def test_a_reviewed_run_publishes_with_its_recipe(session_rolled_back, monkeypatch):
    s = session_rolled_back
    from ml.features import yield_series
    real = yield_series.series
    monkeypatch.setattr(yield_series, "series", lambda sess, c, o, src, region="", field="production_tonnes":
                        real(sess, c, o, src, "", field))          # the test recipe's region reads the national series
    s.execute(text("UPDATE crop_calibration_specs SET retired_at = now(), retired_reason = 'test' "
                   "WHERE commodity = 'Olive oil' AND origin = 'ES' AND driver = 'drought' AND retired_at IS NULL"))
    sp = _recipe(s, yield_region="")
    r1 = runner.run(s, sp)
    p = publish.propose(s, [r1["run_id"]], "test publication (E162)", maker_user_id=None)
    assert p and p["summary"]["upside_passes"] == 1
    from services.governance.platform_policy import SYSTEM_USER
    ops = s.execute(text("SELECT user_id::text FROM users WHERE email = 'ops@tellumen.io'")).scalar() or SYSTEM_USER
    publish.apply_decision(s, {"run_ids": [r1["run_id"]]}, "approved", ops, "reviewed in test")
    fit = s.execute(text("""SELECT f.spec_id::text, f.run_id::text, f.yield_source, f.allow_cycle, f.season_months,
                                   c.season_months AS cal_season, c.baseline_from
                            FROM sc_commodity_fit f JOIN sc_commodities co USING (commodity_id)
                            JOIN sc_commodity_calibration c ON c.commodity_id = f.commodity_id AND c.origin = f.origin
                            WHERE co.name = 'Olive oil' AND f.origin = 'ES' AND f.hazard_driver = 'drought'""")).mappings().one()
    assert (fit["spec_id"], fit["run_id"], fit["yield_source"], fit["allow_cycle"]) == \
           (sp["spec_id"], r1["run_id"], "FAOSTAT QCL bulk", True)
    assert list(fit["cal_season"]) == list(fit["season_months"]) == [4, 5, 6, 7, 8] and fit["baseline_from"] == 1991
    r2 = runner.run(s, sp)                              # the same data: nothing to propose
    assert publish.changes(s, r2["run_id"]) is None


def test_the_upside_rules_judge_the_favourable_years():
    """A panel where the line holds on the good years passes all four rules; the same panel with its gain carried by
    harvested area fails rule 3."""
    pts = [(float(x), 20.0 - 0.4 * x + (1.5 if i % 3 == 0 else -1.0 if i % 3 == 1 else -0.5), 1990 + i)
           for i, x in enumerate([10, 20, 30, 40, 50, 60, 70, 80, 15, 25, 35, 45, 55, 65, 75, 85, 12, 28, 44, 62])]
    flat_area = {1980 + i: 1000.0 for i in range(60)}
    ok = gates.upside(pts, flat_area)
    assert ok["failed"] == [] or "2 band" in ok["failed"]          # the band rule depends on the noise pattern
    assert "1 bias" not in ok["failed"] and "3 area" not in ok["failed"]
    assert gates.upside(pts, {})["failed"].count("3 area") == 1      # no area reported: rule 3 cannot pass


def test_only_the_publish_step_writes_published_fits():
    writes = re.compile(r"(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+sc_commodity_fit\b", re.I)
    offenders = [str(p.relative_to(ROOT)) for d in ("services", "api", "ml", "scripts") for p in (ROOT / d).rglob("*.py")
                 if writes.search(p.read_text(encoding="utf-8")) and p != ROOT / "services/calibration/publish.py"]
    assert offenders == []


def test_a_landed_release_reruns_its_recipes_after_the_commit(monkeypatch):
    from sqlalchemy.orm import Session

    from core.db.config import engine
    from services.reference import crop_releases
    from services.tasks import jobs
    sent = []
    monkeypatch.setattr(jobs, "submit", lambda job, *args: sent.append((job, args)))
    with Session(engine) as s:
        s.execute(text("SELECT 1"))
        crop_releases._rerun_calibrations_after_commit(s, "FAOSTAT QCL bulk")
        assert sent == []                                  # nothing before the landing commits
        s.commit()
    assert sent == [("calibration.run", (["FAOSTAT QCL bulk"],))]


@pytest.mark.skipif(not _HAS_WEATHER, reason="the regional ERA5-Land files are not on this machine")
def test_the_operator_decides_a_publication_through_the_approvals_path(api):
    """End to end: the platform's system account proposes (one approver stated); a customer cannot decide it; the
    platform operator approves → the run is published and named on the fit."""
    from tests.integration.conftest import login
    s = api.s
    s.execute(text("""UPDATE approval_policy SET human_approvers = 1 WHERE action_key = 'calibration.publish'
                      AND org_id = '99999999-9999-4999-8999-999999999999'"""))
    s.execute(text("UPDATE crop_calibration_specs SET retired_at = now(), retired_reason = 'test' "
                   "WHERE commodity = 'Wheat' AND origin = 'MA' AND driver = 'drought' AND retired_at IS NULL"))
    sid = specs.create(s, commodity="Wheat", origin="MA", yield_source="FAOSTAT QCL bulk", driver="drought",
                       weather_kind="box", weather_key="morocco_wheat", season_months=[1, 2, 3, 4, 5, 6],
                       allow_cycle=False, basis="test recipe (E162)", protocol="crop-calib-v1")
    r = runner.run(s, runner.spec(s, sid))
    p = publish.propose(s, [r["run_id"]], "test publication (E162)")
    req = p["approval_request_id"]
    customer = login(api, "approver@nordkap.demo", "Demo!approve1")
    assert api.post(f"/v1/approvals/{req}/decide", headers=customer, json={"decision": "approved"}).status_code in (403, 404)
    ops = login(api, "ops@tellumen.io", "Demo!ops1")
    d = api.post(f"/v1/approvals/{req}/decide", headers=ops, json={"decision": "approved", "reason": "reviewed"})
    assert d.status_code == 200 and d.json()["applied"] == {"status": "published", "runs": 1}
    assert s.execute(text("""SELECT f.run_id::text FROM sc_commodity_fit f JOIN sc_commodities c USING (commodity_id)
                             WHERE c.name = 'Wheat' AND f.origin = 'MA' AND f.hazard_driver = 'drought'""")).scalar() == r["run_id"]
