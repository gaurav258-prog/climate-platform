"""Flood defences in the loss engine (product owner's decisions, 2026-10-16). Rolled back throughout.

  defended    a home with a known protection level: the defended figure beside the undefended one, the line applied
              to the low, central and high curves alike, the level and its basis recorded
  unknown     off the protection map or not sampled: the undefended figure only, labelled 'protection unknown'
  layers      the European maps serve an asset in their countries only once in use, and only where they reach it
  projected   no defended projection: named, not computed"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.loss import curves, engine, protection, registry
from tests.integration.test_loss_engine import (
    _aqueduct_samples,
    _asset,
    _flood_samples,
    _org,
    _results,
    europe_maps,
)

pytestmark = pytest.mark.integration
LAT, LON = 50.0001, 8.0001                     # no demo asset stands here


def _protection(s, status="sampled", rp=150.0, lat=LAT, lon=LON):
    s.execute(text("""INSERT INTO flood_protection_samples (layer_key, layer_version, latitude, longitude, status,
                      design_rp_years) VALUES (:k, :v, :la, :lo, :st, :rp)"""),
              {"k": protection.LAYER, "v": protection.layer()["version"], "la": lat, "lo": lon, "st": status,
               "rp": rp if status == "sampled" else None})


def _europe_samples(s, lat=LAT, lon=LON, status="sampled", caution=None):
    L = registry.layer("jrc_river_flood_europe")
    for rp in L["return_periods"]:
        k = 0.4 + rp / 500
        s.execute(text("""INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell,
                          rp_years, status, value, cell_fraction, cell_mean, caution)
                          VALUES ('jrc_river_flood_europe', :v, :la, :lo, 'test', :rp, :st, :val, :f, :m, :c)"""),
                  {"v": L["version"], "la": lat, "lo": lon, "rp": rp, "st": status,
                   "val": 0.0 if status == "sampled" else None, "f": 0.4 * k if status == "sampled" else None,
                   "m": 1.0 * k if status == "sampled" else None, "c": caution})


@pytest.fixture
def jrc(session_rolled_back, monkeypatch):
    """The JRC family adopted; the European maps pinned as a candidate (a test that needs them in use says so)."""
    if "jrc_huizinga_2017" not in curves.families():
        pytest.skip("the JRC family is not built on this machine")
    s = session_rolled_back
    europe_maps(monkeypatch, "candidate")
    return s, _org(s, {"loss_curve_family_flood": "jrc_huizinga_2017"})


def test_a_protected_home_carries_both_figures(jrc):
    s, org = jrc
    _asset(s, org, country="DE", lat=LAT, lon=LON)
    _flood_samples(s, lat=LAT, lon=LON, share=0.5, depth=1.0)
    _protection(s, rp=150.0)
    f = _results(s, engine.run(s, org, "realestate")["run_id"])["flood"]
    assert f["gap"] is None and f["flood_layer"] == "jrc_river_flood" and f["protection_rp_years"] == 150.0
    assert f["protection_code"] == "loss.protection.level" and f["protection_basis"] == "Defended to 1-in-150 years"
    for band in ("low", "central", "high"):
        losses = {int(k): v[band] for k, v in f["loss_at_rp"].items()}
        col = {"low": "eal_defended_low_eur", "central": "eal_defended_eur", "high": "eal_defended_high_eur"}[band]
        assert float(f[col]) == pytest.approx(protection.defended_eal(losses, 150.0), abs=0.01)
    assert 0 < float(f["eal_defended_eur"]) < float(f["eal_eur"])


def test_unknown_protection_leaves_the_undefended_figure_labelled(jrc):
    s, org = jrc
    _asset(s, org, country="DE", lat=LAT, lon=LON)
    _flood_samples(s, lat=LAT, lon=LON)
    f = _results(s, engine.run(s, org, "realestate")["run_id"])["flood"]
    assert f["eal_eur"] is not None and f["eal_defended_eur"] is None
    assert f["protection_code"] == "loss.protection.not_read" and f["protection_basis"] == "Protection unknown"
    _asset(s, org, country="DE", lat=LAT + 0.01, lon=LON)
    _flood_samples(s, lat=LAT + 0.01, lon=LON)
    _protection(s, status="outside_coverage", lat=LAT + 0.01)
    codes = {r[0] for r in s.execute(text("""SELECT protection_code FROM loss_results WHERE run_id = CAST(:r AS uuid)
        AND peril = 'flood' AND eal_defended_eur IS NULL"""), {"r": engine.run(s, org, "realestate")["run_id"]}).all()}
    assert "loss.protection.off_map" in codes


def test_the_european_maps_serve_only_once_in_use_and_where_they_reach(jrc, monkeypatch):
    s, org = jrc
    _asset(s, org, country="DE", lat=LAT, lon=LON)
    _flood_samples(s, lat=LAT, lon=LON)
    _europe_samples(s, caution="the publisher's caution")
    assert _results(s, engine.run(s, org, "realestate")["run_id"])["flood"]["flood_layer"] == "jrc_river_flood"
    europe_maps(monkeypatch, "in_use")
    f = _results(s, engine.run(s, org, "realestate")["run_id"])["flood"]
    assert f["flood_layer"] == "jrc_river_flood_europe" and len(f["loss_at_rp"]) == 9
    assert f["caution_code"] == "loss.caution.depth_may_be_overstated" and f["caution"] == "Depth may be overstated"
    _asset(s, org, country="DE", lat=LAT + 0.02, lon=LON)          # off the European maps: the global maps serve
    _flood_samples(s, lat=LAT + 0.02, lon=LON)
    _europe_samples(s, lat=LAT + 0.02, status="outside_coverage")
    layers = {r[0] for r in s.execute(text("""SELECT flood_layer FROM loss_results WHERE run_id = CAST(:r AS uuid)
        AND peril = 'flood'"""), {"r": engine.run(s, org, "realestate")["run_id"]}).all()}
    assert layers == {"jrc_river_flood_europe", "jrc_river_flood"}


def test_a_projection_has_no_defended_figure(jrc):
    s, org = jrc
    _asset(s, org, country="DE", lat=LAT, lon=LON)
    _flood_samples(s, lat=LAT, lon=LON)
    _protection(s, rp=150.0)
    A = registry.layer("aqueduct_river_flood")
    today = (A["present"]["scenario"], A["present"]["year"], A["present"]["model"])
    from services.loss import timeline  # the maps hot-house 2050 lies between
    where = timeline.place("aqueduct_river_flood", "hot_house_3_5c", "2050")
    maps = {where["lower"], where["upper"]} - {"present"}
    _aqueduct_samples(s, {today: 0.5, **{(*k.split(":"), m): 1.0 for k in maps for m in A["models"]}}, lat=LAT, lon=LON)
    f = _results(s, engine.run(s, org, "realestate", "hot_house_3_5c", "2050")["run_id"])["flood"]
    assert f["gap"] is None and f["eal_defended_eur"] is None and f["flood_layer"] == "aqueduct_river_flood"
    assert f["protection_code"] == "loss.protection.not_projected" and f["protection_basis"] == "No defended projection"


def test_a_defended_figure_above_the_undefended_one_is_refused(jrc):
    s, org = jrc
    _asset(s, org, country="DE", lat=LAT, lon=LON)
    _flood_samples(s, lat=LAT, lon=LON)
    _protection(s, rp=150.0)
    run_id = engine.run(s, org, "realestate")["run_id"]
    with pytest.raises(Exception):
        with s.begin_nested():
            s.execute(text("""INSERT INTO loss_results (run_id, asset_kind, asset_id, peril, exposed_value_eur, curve_key,
                eal_eur, loss_at_rp, protection_rp_years, eal_defended_eur, eal_defended_low_eur, eal_defended_high_eur)
                VALUES (CAST(:r AS uuid), 'portfolio_entity', gen_random_uuid(), 'flood', 1, 'x', 10, '{}', 100, 11, 11, 11)"""),
                      {"r": run_id})


@pytest.mark.skipif(not (registry.ROOT / protection.layer()["file"]).exists(), reason="the JRC maps are not on this machine")
def test_a_run_samples_what_its_book_is_missing_first(jrc, monkeypatch):
    """A newly added asset gets its figure from the run itself: the run's job samples the flood maps it reads and the
    protection map at locations not yet held (intensity.prepare_book)."""
    from services.loss import intensity
    s, org = jrc
    europe_maps(monkeypatch, "in_use")
    lat, lon = 53.5502, 9.9902                                    # Hamburg, a location no demo asset holds
    _asset(s, org, country="DE", lat=lat, lon=lon)
    assets = engine._assets(s, org, "realestate")
    got = intensity.prepare_book(s, assets, ["flood"])
    assert got[protection.LAYER]["sampled"] >= 1 and got["jrc_river_flood_europe"]["sampled"] >= 1
    assert protection.at(s, lat, lon)[0] == 153.0
    assert intensity.prepare_book(s, assets, ["flood"])[protection.LAYER]["sampled"] == 0      # held: not sampled twice
