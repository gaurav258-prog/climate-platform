"""Coastal flood and the future storm set in the loss engine (the product owner's decisions of 2026-10-23). Rolled back.

  coastal today      water depth by return period from the WRI coastal maps' present day through the adopted depth
                     curves; the curves' river-flood test does not reach it (untested); undefended — no coastal
                     protection level is held; a location in the sea (the maps' no-data) is outside the map, a gap
  coastal projected  read between the maps that bracket the pathway-year's warming; central the 50th percentile of
                     sea-level rise, the range the 5th–95th percentiles' curve-low and curve-high
  storm projected    the STORM future set (+0.83 °C) read against the present set: 2030 served, the wind at each
                     return period blended; central the median of the four models, beside the present set's figure"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.loss import curves, engine, registry, timeline
from tests.integration.test_loss_engine import LAT, LON, _asset, _org, _results

pytestmark = pytest.mark.integration


def _samples(s, key, values: dict, variant=("present", "present", ""), status="sampled", lat=LAT, lon=LON):
    """values: {rp: depth (a water-depth layer) or wind}."""
    L = registry.layer(key)
    depth = L["metric"] == "water_depth"
    for rp, v in values.items():
        wet = depth and v is not None and v > 0
        s.execute(text("""INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell,
                          rp_years, status, value, cell_fraction, cell_mean, scenario, period, climate_model)
                          VALUES (:k, :v, :la, :lo, 'test', :rp, :st, :val, :f, :m, :sc, :per, :mod) ON CONFLICT DO NOTHING"""),
                  {"k": key, "v": L["version"], "la": lat, "lo": lon, "rp": rp, "st": status, "val": v,
                   "f": (1.0 if wet else 0.0) if depth and status == "sampled" else None,
                   "m": (v if wet else 0.0) if depth and status == "sampled" else None,
                   "sc": variant[0], "per": variant[1], "mod": variant[2]})


def _coast(scale: float) -> dict:
    return {rp: round(scale * k, 3) for rp, k in zip(registry.layer("aqueduct_coastal_flood")["return_periods"],
                                                     (0, 0, 0.2, 0.4, 0.6, 1.0, 1.3, 1.5, 1.7))}


@pytest.fixture()
def coastal_org(session_rolled_back):
    s = session_rolled_back
    if "jrc_huizinga_2017" not in curves.families():
        pytest.skip("the JRC curves are not registered on this machine")
    org = _org(s, {"loss_curve_family_coastal_flood": "jrc_huizinga_2017"})
    _asset(s, org)
    return s, org


def test_today_s_coastal_figure_is_read_through_the_depth_curves_untested_and_undefended(coastal_org):
    s, org = coastal_org
    _samples(s, "aqueduct_coastal_flood", _coast(1.0))
    c = _results(s, engine.run(s, org, "realestate")["run_id"])["coastal_flood"]
    assert c["gap"] is None and float(c["eal_eur"]) > 0 and c["flood_layer"] == "aqueduct_coastal_flood"
    assert c["standing"] == "untested"                           # the curves' river-flood test does not reach coast
    assert c["protection_code"] == "loss.protection.coastal_not_held" and c["eal_defended_eur"] is None
    assert float(c["eal_low_eur"]) <= float(c["eal_eur"]) <= float(c["eal_high_eur"])


def test_a_place_in_the_sea_is_outside_the_coastal_map(coastal_org):
    s, org = coastal_org
    _samples(s, "aqueduct_coastal_flood", {rp: None for rp in _coast(1.0)}, status="outside_coverage")
    c = _results(s, engine.run(s, org, "realestate")["run_id"])["coastal_flood"]
    assert c["gap_code"] == "loss.gap.outside_map" and c["eal_eur"] is None


def test_a_coastal_projection_reads_the_50th_percentile_with_the_5th_to_95th_as_its_range(coastal_org):
    s, org = coastal_org
    where = timeline.place("aqueduct_coastal_flood", "hot_house_3_5c", "2050")
    _samples(s, "aqueduct_coastal_flood", _coast(1.0))
    for key in {where["lower"], where["upper"]} - {"present"}:
        pathway, period = key.split(":")
        for m, scale in (("p05", 1.2), ("p50", 1.5), ("p95", 2.0)):
            _samples(s, "aqueduct_coastal_flood", _coast(scale), (pathway, period, m))
    c = _results(s, engine.run(s, org, "realestate", "hot_house_3_5c", "2050")["run_id"])["coastal_flood"]
    eal = {m: float(v) for m, v in c["model_eal"].items()}
    assert set(eal) == {"p05", "p50", "p95"} and float(c["eal_eur"]) == pytest.approx(eal["p50"])
    assert float(c["eal_low_eur"]) <= eal["p05"] and float(c["eal_high_eur"]) >= eal["p95"]
    assert float(c["eal_same_source_today_eur"]) < float(c["eal_eur"]) and c["standing"] == "untested"


def test_the_future_storm_set_serves_2030_between_the_present_and_its_warming(session_rolled_back):
    s = session_rolled_back
    if "eberenz_2021_rmsf" not in curves.families():
        pytest.skip("the cyclone curves are not registered on this machine")
    org = _org(s, {"loss_curve_family_storm": "eberenz_2021_rmsf"})
    _asset(s, org)
    rps = registry.layer("storm_v4_wind")["return_periods"]
    _samples(s, "storm_v4_wind", {rp: 20.0 + 5 * i for i, rp in enumerate(rps)})
    L = registry.layer("storm_cc_wind")
    for j, m in enumerate(L["models"]):                       # each model a little windier than today
        _samples(s, "storm_cc_wind", {rp: 22.0 + j + 5 * i for i, rp in enumerate(rps)}, ("ssp585", "2015-2050", m))
    out = engine.run(s, org, "realestate", "hot_house_3_5c", "2030")
    st = _results(s, out["run_id"])["storm"]
    eal = sorted(float(v) for v in st["model_eal"].values())
    assert st["gap"] is None and len(eal) == 4
    assert float(st["eal_eur"]) == pytest.approx((eal[1] + eal[2]) / 2, abs=0.01)     # the median of four
    assert float(st["eal_same_source_today_eur"]) < float(st["eal_eur"])
    run = s.execute(text("SELECT inputs FROM loss_runs WHERE run_id = CAST(:r AS uuid)"), {"r": out["run_id"]}).scalar()
    placed = run["layers"]["storm"]["placement"]
    assert (placed["lower"], placed["upper"]) == ("present", "ssp585:2015-2050") and 0 < placed["w"] < 1
    later = _results(s, engine.run(s, org, "realestate", "hot_house_3_5c", "2050")["run_id"])["storm"]
    assert later["gap_code"] == "loss.gap.beyond_warming"
