"""E169: the loss foundation's data model holds its rules in the database. Rolled back throughout.

  intensity   a sample outside coverage carries no value (never a zero); samples never change
  occupancy   only the registered classes; an asset's stated use is kept
  runs        a loss run, its results and its curve never change; a result is a figure or a named gap, not both
  buildings   a match is appended, never edited; the latest is the highest match_id"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _fails(s, sql: str, params: dict | None = None, match: str | None = None):
    with pytest.raises(Exception, match=match):
        with s.begin_nested():
            s.execute(text(sql), params or {})


def test_an_intensity_outside_coverage_has_no_value_and_samples_never_change(session_rolled_back):
    s = session_rolled_back
    ins = """INSERT INTO hazard_intensity_samples (layer_key, layer_version, latitude, longitude, h3_cell, rp_years,
             status, value, cell_fraction, cell_mean) VALUES ('jrc_river_flood', 'v2.1.2', 41.4, 2.17, 'c', :rp, :st, :v, :f, :m)"""
    s.execute(text(ins), {"rp": 100, "st": "sampled", "v": 0.8, "f": 0.3, "m": 0.6})
    _fails(s, ins, {"rp": 10, "st": "outside_coverage", "v": 0.0, "f": None, "m": None})
    _fails(s, ins, {"rp": 500, "st": "sampled", "v": None, "f": None, "m": None})
    _fails(s, "UPDATE hazard_intensity_samples SET value = 1.0 WHERE layer_key = 'jrc_river_flood' AND h3_cell = 'c'",
           match="append-only")
    _fails(s, "DELETE FROM hazard_intensity_samples WHERE h3_cell = 'c'", match="append-only")


def test_occupancy_is_a_registered_class(session_rolled_back):
    s = session_rolled_back
    eid = s.execute(text("SELECT entity_id FROM portfolio_entities LIMIT 1")).scalar()
    if eid is None:
        pytest.skip("no portfolio entity on this database")
    s.execute(text("UPDATE portfolio_entities SET occupancy = 'residential' WHERE entity_id = :e"), {"e": eid})
    _fails(s, "UPDATE portfolio_entities SET occupancy = 'hotel' WHERE entity_id = :e", {"e": eid})


def test_a_loss_run_and_its_results_never_change(session_rolled_back):
    s = session_rolled_back
    org = s.execute(text("SELECT org_id FROM organizations LIMIT 1")).scalar()
    run = s.execute(text("""INSERT INTO loss_runs (org_id, book, scenario, time_horizon, as_of, engine_version, inputs,
                                n_assets, n_gaps)
                            VALUES (:o, 'realestate', 'baseline', 'current', '2026-10-06', 'test', '{}', 2, 1)
                            RETURNING run_id"""), {"o": org}).scalar()
    res = """INSERT INTO loss_results (run_id, asset_kind, asset_id, peril, exposed_value_eur, occupancy, curve_key,
             eal_eur, loss_at_rp, gap) VALUES (:r, 'portfolio_entity', gen_random_uuid(), 'flood', :val, 'commercial',
             :c, :eal, CAST(:rp AS jsonb), :gap)"""
    s.execute(text(res), {"r": run, "val": 1e6, "c": "huizinga_2017:commercial:europe", "eal": 1234.5,
                          "rp": json.dumps({"100": 50000}), "gap": None})
    s.execute(text(res), {"r": run, "val": 1e6, "c": None, "eal": None, "rp": None, "gap": "no curve family adopted for flood"})
    _fails(s, res, {"r": run, "val": 1e6, "c": "x", "eal": 10.0, "rp": json.dumps({"100": 1}), "gap": "both"})
    _fails(s, res, {"r": run, "val": 1e6, "c": None, "eal": 10.0, "rp": json.dumps({"100": 1}), "gap": None})
    s.execute(text("""INSERT INTO loss_ep_points (run_id, peril, kind, rp_years, loss_eur, basis)
                      VALUES (:r, 'flood', 'aep', 200, 9e5, 'stated_dependence')"""), {"r": run})
    for sql in ("UPDATE loss_runs SET n_gaps = 0 WHERE run_id = :r", "DELETE FROM loss_runs WHERE run_id = :r",
                "UPDATE loss_results SET eal_eur = 0 WHERE run_id = :r", "UPDATE loss_ep_points SET loss_eur = 0 WHERE run_id = :r"):
        _fails(s, sql, {"r": run}, match="append-only")


def test_a_building_match_is_appended_and_the_latest_is_the_highest_id(session_rolled_back):
    s = session_rolled_back
    aid = s.execute(text("SELECT gen_random_uuid()")).scalar()
    ins = """INSERT INTO asset_building_matches (asset_kind, asset_id, source_key, source_version, status, building_ref,
             footprint_area_m2, distance_m) VALUES ('portfolio_entity', :a, 'overture', :v, :st, :b, :ar, :d) RETURNING match_id"""
    first = s.execute(text(ins), {"a": aid, "v": "2026-09", "st": "no_building", "b": None, "ar": None, "d": None}).scalar()
    second = s.execute(text(ins), {"a": aid, "v": "2026-10", "st": "matched", "b": "08b1", "ar": 412.0, "d": 3.2}).scalar()
    _fails(s, ins, {"a": aid, "v": "x", "st": "matched", "b": None, "ar": None, "d": None})
    latest = s.execute(text("""SELECT status FROM asset_building_matches WHERE asset_id = :a
                               ORDER BY match_id DESC LIMIT 1"""), {"a": aid}).scalar()
    assert second > first and latest == "matched"
    _fails(s, "UPDATE asset_building_matches SET status = 'no_building' WHERE match_id = :m", {"m": second}, match="append-only")
