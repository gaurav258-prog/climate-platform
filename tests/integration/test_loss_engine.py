"""E171: the loss engine walks every asset and peril through the decision tree. Rolled back throughout.

  gaps        no family adopted, use not stated, no curve for the country, a grouping ('EU') for a country, no building
              value (a market value is never read as one) — each named, never a zero
  figure      a US home on a flooded cell: a range with low ≤ central ≤ high, the expected annual loss the area under
              the loss–exceedance curve, the standing the curve's test gave (the measured family failed → held)
  book curve  only published figures are added, and only on the stated dependence"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from services.loss import curves, engine

pytestmark = pytest.mark.integration
LAT, LON = 29.7631, -95.3701


def _org(s, elections: dict) -> str:
    org = s.execute(text("SELECT org_id::text FROM organizations LIMIT 1")).scalar()
    s.execute(text("""INSERT INTO org_calc_settings (org_id, interpretation, updated_at) VALUES (CAST(:o AS uuid),
                      CAST(:i AS jsonb), now()) ON CONFLICT (org_id) DO UPDATE SET interpretation =
                      COALESCE(org_calc_settings.interpretation, '{}'::jsonb) || CAST(:i AS jsonb)"""),
              {"o": org, "i": json.dumps(elections)})
    s.execute(text("UPDATE portfolio_entities SET source = 'supervisor_shadow' WHERE org_id = CAST(:o AS uuid) "
                   "AND vertical = 'realestate' AND source = 'own'"), {"o": org})   # the book holds only the test assets
    return org


def _asset(s, org, **kw) -> str:
    """A property with a market value of 600,000 and, unless `building` says otherwise, a building value of 400,000."""
    row = {"lat": LAT, "lon": LON, "country": "US", "occ": "residential", "type": "property", "building": 400000.0, **kw}
    eid = s.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, latitude, longitude, country,
                                        primary_value_eur, occupancy, source)
        VALUES (gen_random_uuid(), CAST(:o AS uuid), 'realestate', 'test asset', :type, :lat, :lon, :country, 600000, :occ,
                'own') RETURNING entity_id::text"""), {"o": org, **row}).scalar()
    s.execute(text("""INSERT INTO ext_realestate (entity_id, annual_noi_eur, building_value_eur)
                      VALUES (CAST(:e AS uuid), 1, :b)"""), {"e": eid, "b": row["building"]})
    return eid


def _flood_samples(s, lat=LAT, lon=LON, share=0.5, depth=1.0):
    for rp, k in ((10, 0.6), (100, 1.0), (500, 1.3)):
        s.execute(text("""INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell,
                          rp_years, status, value, cell_fraction, cell_mean)
                          VALUES ('jrc_river_flood', 'v2.1.2', :la, :lo, 'test', :rp, 'sampled', 0, :f, :m)
                          ON CONFLICT DO NOTHING"""), {"la": lat, "lo": lon, "rp": rp, "f": share * k, "m": depth * k})


def europe_maps(monkeypatch, status: str) -> None:
    """Pin the JRC European maps' status for a test: whether they serve European assets is the registry's state, which
    their check changes (services.loss.europe_check) — a test states which one it assumes."""
    from services.loss import registry
    L = {**registry.layers()}
    L["jrc_river_flood_europe"] = {**L["jrc_river_flood_europe"], "status": status}
    monkeypatch.setattr(registry, "layers", lambda: L)


def _results(s, run_id) -> dict:
    return {r["peril"]: dict(r) for r in s.execute(text(
        "SELECT * FROM loss_results WHERE run_id = CAST(:r AS uuid)"), {"r": run_id}).mappings()}


def test_every_missing_input_is_a_named_gap(session_rolled_back, monkeypatch):
    s = session_rolled_back
    europe_maps(monkeypatch, "candidate")              # the Spanish asset below reads the global maps
    if "nfip_measured" not in curves.families():
        pytest.skip("the measured family is not built on this machine")
    org = _org(s, {})
    _asset(s, org)
    _flood_samples(s)
    r = _results(s, engine.run(s, org, "realestate")["run_id"])
    assert r["flood"]["gap_code"] == "loss.gap.no_curves_chosen" and r["flood"]["eal_eur"] is None
    assert r["flood"]["gap"] == "No damage curves chosen" and r["flood"]["gap_params"] == {"peril": "river flood"}
    assert r["storm"]["gap_code"] in ("loss.gap.not_read", "loss.gap.outside_map", "loss.gap.no_curves_chosen")
    s.execute(text("""UPDATE org_calc_settings SET interpretation = interpretation || '{"loss_curve_family_flood": "nfip_measured"}'
                      WHERE org_id = CAST(:o AS uuid)"""), {"o": org})
    _asset(s, org, occ=None, type="logistics", lat=LAT + 0.001)
    _flood_samples(s, lat=LAT + 0.001)
    _asset(s, org, country="ES", lat=LAT + 0.002)
    _flood_samples(s, lat=LAT + 0.002)
    _asset(s, org, building=None, lat=LAT + 0.003)
    _flood_samples(s, lat=LAT + 0.003)
    _asset(s, org, country="EU", lat=LAT + 0.004)
    _flood_samples(s, lat=LAT + 0.004)
    gaps = {(c, json.dumps(p, sort_keys=True)) for (c, p) in s.execute(text("""SELECT gap_code, gap_params FROM loss_results
        WHERE run_id = CAST(:r AS uuid) AND peril = 'flood'"""), {"r": engine.run(s, org, "realestate")["run_id"]}).all()}
    codes = {c for c, _p in gaps}
    assert ("loss.gap.use_unknown", json.dumps({"type": "logistics"})) in gaps
    assert ("loss.gap.no_curve", json.dumps({"country": "Spain", "use": "residential"})) in gaps
    assert "loss.gap.no_building_value" in codes
    assert ("loss.gap.country_group", json.dumps({"hint": " Its coordinates are in United States.", "stated": "EU"},
                                                  sort_keys=True)) in gaps


def test_a_us_home_on_a_flooded_cell_gets_a_range_with_its_standing(session_rolled_back):
    s = session_rolled_back
    fam = curves.families().get("nfip_measured")
    if fam is None:
        pytest.skip("the measured family is not built on this machine")
    org = _org(s, {"loss_curve_family_flood": "nfip_measured"})
    _asset(s, org)
    _flood_samples(s, share=0.5, depth=1.0)
    r = _results(s, engine.run(s, org, "realestate")["run_id"])["flood"]
    assert r["gap"] is None and r["curve_key"] == "nfip_measured:residential:united_states"
    assert r["standing"] == ("published" if fam["test"]["passed"] else "held")
    assert r["eal_low_eur"] <= r["eal_eur"] <= r["eal_high_eur"]
    rp = r["loss_at_rp"]
    assert rp["100"]["central"] == pytest.approx(400000 * 0.5 * curves.ratio(fam["curves"][0]["points"], 1.0), rel=1e-6)
    assert float(r["exposed_value_eur"]) == 400000                  # the building's value, not the 600,000 market value
    central = {int(k): v["central"] for k, v in rp.items()}
    assert float(r["eal_eur"]) == pytest.approx(engine.eal(central), abs=0.01)


def test_the_book_curve_adds_only_published_figures_on_the_stated_dependence(session_rolled_back, monkeypatch):
    s = session_rolled_back
    fam = curves.families().get("nfip_measured")
    if fam is None:
        pytest.skip("the measured family is not built on this machine")
    passed = {**fam, "family": "test_passed", "test": {**fam["test"], "passed": True}}
    monkeypatch.setattr(curves, "families", lambda: {**curves._load()[0], "test_passed": passed})
    org = _org(s, {"loss_curve_family_flood": "test_passed"})
    _asset(s, org)
    _flood_samples(s)
    assert engine.run(s, org, "realestate")["ep_points"] == 0           # no dependence stated → no book curve
    s.execute(text("""UPDATE org_calc_settings SET interpretation = interpretation || '{"loss_flood_dependence": "comonotonic"}'
                      WHERE org_id = CAST(:o AS uuid)"""), {"o": org})
    out = engine.run(s, org, "realestate")
    assert out["ep_points"] == 3
    ep = dict(s.execute(text("SELECT rp_years, CAST(loss_eur AS FLOAT) FROM loss_ep_points WHERE run_id = CAST(:r AS uuid)"),
                        {"r": out["run_id"]}).all())
    res = _results(s, out["run_id"])["flood"]
    assert ep[100] == pytest.approx(res["loss_at_rp"]["100"]["central"], abs=0.01)


def test_eal_is_the_area_under_the_exceedance_curve():
    assert engine.eal({10: 100.0, 100: 1000.0, 500: 2000.0}) == pytest.approx(
        (0.1 - 0.01) * 550 + (0.01 - 0.002) * 1500 + 0.002 * 2000)


def _aqueduct_samples(s, depths: dict, lat=LAT, lon=LON):
    """depths: {(scenario, period, model): 1-in-100 depth}; 1-in-10 and 1-in-500 scale by 0.6 and 1.3."""
    from services.loss import registry
    v = registry.layer("aqueduct_river_flood")["version"]
    for (sc, per, m), d in depths.items():
        for rp, k in ((10, 0.6), (100, 1.0), (500, 1.3)):
            s.execute(text("""INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell,
                              rp_years, status, value, cell_fraction, cell_mean, scenario, period, climate_model)
                              VALUES ('aqueduct_river_flood', :v, :la, :lo, 'test', :rp, 'sampled', :d, :f, :d, :sc, :per, :m)
                              ON CONFLICT DO NOTHING"""),
                      {"v": v, "la": lat, "lo": lon, "rp": rp, "d": d * k, "f": 1.0 if d > 0 else 0.0, "sc": sc, "per": per,
                       "m": m})


def test_a_projection_reads_the_middle_model_and_the_same_sources_today(session_rolled_back):
    """Product owner's decisions (2026-10-07): the projection source's own depths; the middle model as the central
    figure, the models' lowest and highest as the range; beside it the same source's present day."""
    from services.loss import registry
    s = session_rolled_back
    fam = curves.families().get("nfip_measured")
    if fam is None:
        pytest.skip("the measured family is not built on this machine")
    L = registry.layer("aqueduct_river_flood")
    org = _org(s, {"loss_curve_family_flood": "nfip_measured"})
    _asset(s, org)
    _flood_samples(s)
    today = (L["present"]["scenario"], L["present"]["year"], L["present"]["model"])
    depths = {today: 0.5, **{("rcp8p5", "2050", m): d for m, d in zip(L["models"], (0.4, 0.8, 1.2, 1.6, 2.0))}}
    _aqueduct_samples(s, depths)
    out = engine.run(s, org, "realestate", "hot_house_3_5c", "2050")
    r = _results(s, out["run_id"])
    f = r["flood"]
    assert f["gap"] is None and f["standing"] in ("held", "published", "untested")
    model_eal = {m: float(v) for m, v in f["model_eal"].items()}
    assert len(model_eal) == 5 and float(f["eal_eur"]) == sorted(model_eal.values())[2]      # the middle model
    assert float(f["eal_low_eur"]) <= min(model_eal.values()) and float(f["eal_high_eur"]) >= max(model_eal.values())
    assert float(f["eal_same_source_today_eur"]) < float(f["eal_eur"])                      # deeper water than today
    assert r["storm"]["gap_code"] == "loss.gap.no_projection_peril" and r["storm"]["gap"] == "No projection for this hazard"
    run = s.execute(text("SELECT inputs FROM loss_runs WHERE run_id = CAST(:r AS uuid)"), {"r": out["run_id"]}).scalar()
    assert run["layers"]["flood"]["pathway"] == "rcp8p5" and run["layers"]["flood"]["period"] == "2050"


def test_a_scenario_or_horizon_the_source_does_not_publish_is_a_named_gap(session_rolled_back):
    s = session_rolled_back
    org = _org(s, {"loss_curve_family_flood": "nfip_measured"})
    _asset(s, org)
    r = _results(s, engine.run(s, org, "realestate", "orderly_1_5c", "2050")["run_id"])["flood"]
    assert r["gap_code"] == "loss.gap.no_projection_scenario" and r["gap_params"] == {"scenario": "Orderly 1.5 °C"}
    r = _results(s, engine.run(s, org, "realestate", "disorderly_2c", "2100")["run_id"])["flood"]
    assert r["gap_code"] == "loss.gap.no_projection_year" and r["gap_params"] == {"year": "2100"}
    with pytest.raises(ValueError):
        engine.run(s, org, "realestate", "baseline", "2050")
    with pytest.raises(ValueError):
        engine.run(s, org, "realestate", "hot_house_3_5c", "current")


def test_each_jrc_curve_carries_its_own_test_and_an_untested_one_says_so(session_rolled_back, monkeypatch):
    """Product owner's decisions (2026-10-07): the JRC curves cover the UN M49 region's countries; Europe publishes no
    spread, so its figure has no range; a curve tested on its own carries that test's standing, every other is
    untested. The European residential curve was tested on HANZE's reported regional losses (2026-10-20,
    loss_protocol.json europe_loss_test) and held; the North American one on US claims and held; the Latin American
    one is untested."""
    s = session_rolled_back
    europe_maps(monkeypatch, "candidate")              # the German home reads the global maps
    fam = curves.families().get("jrc_huizinga_2017")
    if fam is None:
        pytest.skip("the JRC family is not built on this machine")
    org = _org(s, {"loss_curve_family_flood": "jrc_huizinga_2017"})
    _asset(s, org, country="DE", lat=50.94, lon=6.96)
    _flood_samples(s, lat=50.94, lon=6.96, share=0.5, depth=1.0)
    _asset(s, org, country="US")
    _flood_samples(s)
    _asset(s, org, country="BR", lat=-23.55, lon=-46.63)
    _flood_samples(s, lat=-23.55, lon=-46.63)
    rows = {r["curve_key"]: dict(r) for r in s.execute(text("""SELECT * FROM loss_results WHERE run_id = CAST(:r AS uuid)
            AND peril = 'flood'"""), {"r": engine.run(s, org, "realestate")["run_id"]}).mappings()}
    de, us = rows["jrc_huizinga_2017:residential:150"], rows["jrc_huizinga_2017:residential:021"]
    br = rows["jrc_huizinga_2017:residential:419"]
    eu_curve = next(c for c in fam["curves"] if c["key"] == "jrc_huizinga_2017:residential:150")
    assert eu_curve["test"]["protocol"] == "europe_loss_test"
    assert de["standing"] == ("published" if eu_curve["test"]["passed"] else "held")
    assert de["eal_low_eur"] == de["eal_eur"] == de["eal_high_eur"]
    assert de["loss_at_rp"]["100"]["central"] == pytest.approx(400000 * 0.5 * curves.ratio(eu_curve["points"], 1.0), rel=1e-6)
    assert us["standing"] == "held" and us["eal_low_eur"] < us["eal_eur"] < us["eal_high_eur"]
    assert br["standing"] == "untested"
