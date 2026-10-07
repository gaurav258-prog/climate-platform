"""E171/E172: the 30 m refinement re-spreads the mapped water over the terrain by the protocol's stated method, and
reads the 90 m maps exactly as the validator does."""
from __future__ import annotations

import numpy as np
import pytest

from services.loss.refine30 import respread


def test_water_settles_to_the_surface_of_its_90m_pixel():
    # one wet 90 m pixel, three sub-pixels at 10, 11, 12 m, mapped depth 1 m → surface 12 m → 2 m, 1 m, dry
    got = respread(np.array([7, 7, 7]), np.array([10.0, 11.0, 12.0]), np.array([1.0, 1.0, 1.0]))
    assert sorted(got.tolist()) == [1.0, 2.0]


def test_each_90m_pixel_keeps_its_own_surface():
    got = respread(np.array([1, 1, 2, 2]), np.array([0.0, 2.0, 100.0, 100.0]), np.array([0.5, 0.5, 0.3, 0.3]))
    assert sorted(np.round(got, 6).tolist()) == [0.3, 0.3, 1.5]      # pixel 1: surface 1.5; pixel 2: flat, 0.3 m


def test_nothing_wet_gives_nothing():
    assert respread(np.array([], dtype=int), np.array([]), np.array([])).size == 0


def test_the_90m_reading_is_the_validators(monkeypatch):
    from shapely.geometry import box

    from ml.scoring.flood_jrc import TileSet
    from services.loss.refine30 import box_stats, dem_paths
    b = box(11.9, 44.4, 12.0, 44.5)                                   # Emilia-Romagna, inside a test tile
    if dem_paths(*b.bounds) is None or TileSet().stats(b) is None:
        pytest.skip("the flood maps or the terrain tiles are not on this machine")
    st, ref = box_stats(b), TileSet().stats(b)
    assert st["m90"][0] == pytest.approx(ref[100][0]) and st["m90"][1] == pytest.approx(ref[100][1])


def test_csi_counts_hits_against_misses_and_false_alarms():
    from services.loss.refine30 import _scores
    s = _scores({"hits": 30, "misses": 10, "false_alarms": 20})
    assert s["csi"] == 0.5 and s["hit_rate"] == 0.75 and s["false_alarm_ratio"] == 0.4
    assert _scores({"hits": 0, "misses": 0, "false_alarms": 0})["csi"] is None


def test_the_respread_can_narrow_a_flood_but_never_widen_it():
    # every 30 m depth comes from a wet 90 m parent: a dry parent contributes nothing, so the 30 m wet set is a subset
    from services.loss.refine30 import respread_depths
    d = respread_depths(np.array([1, 1, 1, 1]), np.array([10.0, 10.2, 10.4, 11.6]), np.array([0.3, 0.3, 0.3, 0.3]))
    assert (d > 0.05).sum() == 3 and d[3] < 0                         # the high corner is dry, the rest stay wet


def test_a_recorded_decision_survives_a_rerun_of_the_test(tmp_path, monkeypatch):
    import json

    from services.loss import refine30
    f = tmp_path / "layers.json"
    decision = {"by": "product owner", "date": "2026-10-07", "outcome": "keep the 90 m maps", "basis": "x"}
    f.write_text(json.dumps({"layers": {"jrc_flood_30m": {"decision": decision, "building_scale_test": {"verdict": "cannot tell"}}}}))
    monkeypatch.setattr(refine30, "LAYERS_FILE", f)
    refine30.record({"passed": True, "difference_90pct_interval": {"rho": [-0.002, 0.005], "auc": [-0.001, 0.004]}})
    L = json.loads(f.read_text())["layers"]["jrc_flood_30m"]
    assert L["decision"] == decision and L["building_scale_test"]["verdict"] == "cannot tell"
    assert L["status"] == "candidate" and L["adoption"] == "decided 2026-10-07: keep the 90 m maps"
