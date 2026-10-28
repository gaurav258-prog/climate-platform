"""European windstorm in the loss engine (the product owner's decisions of 2026-10-25). Rolled back.

  today        each return period's gust from the PRIMAVERA gust maps through the adopted windstorm curve (Prahl et al.
               2015, German homes): low, central and high from the curve's published range; untested — no observed
               European storm losses are held to test it
  where not    a home outside Germany, or a building of another use, has no curve: a named gap
  beside       a hazard of its own: the tropical-cyclone result of the same asset stands apart, never added
  projected    no projection source: a named gap"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.loss import curves, engine, registry
from services.loss import windstorm_events as W
from tests.integration.test_loss_coastal_storm import _samples
from tests.integration.test_loss_engine import _asset, _org, _results

pytestmark = pytest.mark.integration

BERLIN = (52.52, 13.405)
GUSTS = (24.0, 27.0, 29.5, 32.0, 34.5, 35.0, 38.0, 41.0)         # one per registered return period, rising


@pytest.fixture()
def windstorm_org(session_rolled_back):
    s = session_rolled_back
    if "prahl_2015_h" not in curves.families():
        pytest.skip("the windstorm curves are not registered on this machine")
    org = _org(s, {"loss_curve_family_windstorm": "prahl_2015_h"})
    return s, org


def _gusts(s, lat, lon):
    rps = registry.layer(W.LAYER)["return_periods"]
    _samples(s, W.LAYER, dict(zip(rps, GUSTS)), lat=lat, lon=lon)
    return dict(zip(rps, GUSTS))


def test_a_german_home_reads_each_return_period_s_gust_through_the_curve_and_its_range(windstorm_org):
    s, org = windstorm_org
    _asset(s, org, lat=BERLIN[0], lon=BERLIN[1], country="DE")
    gust = _gusts(s, *BERLIN)
    out = engine.run(s, org, "realestate")
    w = _results(s, out["run_id"])["windstorm"]
    c = curves.curve_for("prahl_2015_h", "residential", "DE")
    assert w["gap"] is None and w["curve_key"] == c["key"] and w["standing"] == "untested"
    for rp, g in gust.items():
        band = w["loss_at_rp"][str(rp)]
        assert band["central"] == pytest.approx(400000 * curves.ratio(c["points"], g), abs=0.01)
        assert band["low"] == pytest.approx(400000 * curves.ratio(c["range_points"]["low"], g), abs=0.01)
        assert band["high"] == pytest.approx(400000 * curves.ratio(c["range_points"]["high"], g), abs=0.01)
    central = {rp: 400000 * curves.ratio(c["points"], g) for rp, g in gust.items()}
    assert float(w["eal_eur"]) == pytest.approx(engine.eal(central), abs=0.01)
    assert float(w["eal_low_eur"]) < float(w["eal_eur"]) < float(w["eal_high_eur"])
    run = s.execute(text("SELECT inputs FROM loss_runs WHERE run_id = CAST(:r AS uuid)"), {"r": out["run_id"]}).scalar()
    assert run["layers"]["windstorm"]["key"] == W.LAYER
    assert run["readings"]["windstorm"] == {"layer": W.LAYER, "metric": "max_gust_3s_10m", "divide_by": 1.0}


def test_a_home_outside_germany_and_a_german_office_have_no_curve(windstorm_org):
    s, org = windstorm_org
    paris = _asset(s, org, lat=48.857, lon=2.352, country="FR")
    office = _asset(s, org, lat=BERLIN[0], lon=BERLIN[1], country="DE", occ="commercial")
    _gusts(s, 48.857, 2.352)
    _gusts(s, *BERLIN)
    run = engine.run(s, org, "realestate")["run_id"]
    got = {str(r["asset_id"]): dict(r) for r in s.execute(text(
        "SELECT * FROM loss_results WHERE run_id = CAST(:r AS uuid) AND peril = 'windstorm'"), {"r": run}).mappings()}
    assert got[paris]["gap_code"] == got[office]["gap_code"] == "loss.gap.no_curve"
    assert got[paris]["gap_params"]["country"] == "France" and got[office]["gap_params"]["use"] == "commercial"


def test_windstorm_stands_beside_tropical_cyclone_never_added(windstorm_org):
    s, org = windstorm_org
    _asset(s, org, lat=BERLIN[0], lon=BERLIN[1], country="DE")
    _gusts(s, *BERLIN)
    r = _results(s, engine.run(s, org, "realestate")["run_id"])
    assert r["windstorm"]["gap"] is None and r["storm"]["gap_code"] == "loss.gap.no_curves_chosen"
    assert {"flood", "coastal_flood", "storm", "windstorm"} <= set(r)


def test_a_location_off_the_gust_maps_is_outside_the_map(windstorm_org):
    s, org = windstorm_org
    _asset(s, org, lat=BERLIN[0], lon=BERLIN[1], country="DE")
    rps = registry.layer(W.LAYER)["return_periods"]
    _samples(s, W.LAYER, {rp: None for rp in rps}, status="outside_coverage", lat=BERLIN[0], lon=BERLIN[1])
    w = _results(s, engine.run(s, org, "realestate")["run_id"])["windstorm"]
    assert w["gap_code"] == "loss.gap.outside_map"


def test_a_projected_windstorm_figure_is_a_named_gap(windstorm_org):
    s, org = windstorm_org
    _asset(s, org, lat=BERLIN[0], lon=BERLIN[1], country="DE")
    _gusts(s, *BERLIN)
    w = _results(s, engine.run(s, org, "realestate", "hot_house_3_5c", "2030")["run_id"])["windstorm"]
    assert w["gap_code"] == "loss.gap.no_projection_peril"
