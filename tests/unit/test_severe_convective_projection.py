"""Severe convective storms project their ENVIRONMENT forward: warming never lowers the score (AR6: CAPE increases,
high confidence), every number the projection uses is cited in reference data, and the projection-posture registry
states exactly what the scorer does."""
import json
import os

import pytest

import ml.scoring.severe_convective_point as point
from ml.scoring.cmip6 import GLOBAL_NPZ, Cmip6Delta, cmip6_delta_latlon
from ml.scoring.projection_coverage import projection_coverage
from ml.scoring.severe_convective_point import anchor_ceiling, damage_anchored_score
from ml.scoring.severe_convective_projection import (
    REFERENCE,
    cape_rates,
    project_potential,
    reference,
)


def _delta(dt, std=0.0, n=4):
    return Cmip6Delta(dt, 0.0, n, std, 0.0)


def test_every_projection_number_is_cited_in_reference_data():
    ref = json.load(open(REFERENCE))
    m = ref["mechanism"]
    assert m["cape_rate_per_k"] == {"low": 0.06, "high": 0.07} and "Romps" in m["_rate_source"] and "6%–7%" in m["_rate_source"]
    assert m["index_exponent_on_cape"] == 0.5 and "sqrt(2·CAPE)" in m["_index_source"]
    assert "11.7.3.5" in m["_shear_source"]
    sources = " ".join(x["source"] for x in ref["literature"])
    for cite in ("§11.7.3.5", "§12.4.5.3", "Rädler", "Chen"):
        assert cite in sources
    assert all(x["confidence"] for x in ref["literature"])
    joined = " ".join(ref["not_projected"])
    assert "event frequency" in joined and "hail size" in joined and "shear" in joined


def test_warming_never_lowers_the_score():
    lo, mid, hi = cape_rates()
    assert lo < mid < hi
    for pot in [0.5 * i for i in range(201)]:
        today = damage_anchored_score(pot)
        prev = today
        for dt in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0):
            p = project_potential(pot, _delta(dt, std=0.4))
            s = damage_anchored_score(p.central)
            assert s >= prev >= today, (pot, dt)
            assert p.lower <= p.central <= p.upper
            assert damage_anchored_score(p.lower) <= s <= damage_anchored_score(p.upper)
            prev = s


def test_no_pathway_means_todays_value_and_no_band():
    p = project_potential(37.0, None)             # baseline / current: no CMIP6 pathway
    assert p == (37.0, None, None, None)
    p1 = project_potential(37.0, _delta(2.0, n=1))  # one model: a point, never a fake band
    assert p1.lower is None and p1.upper is None and p1.central > 37.0


def test_cape_rate_moves_the_index_by_its_square_root():
    _, mid, _ = cape_rates()
    p = project_potential(40.0, _delta(3.0))
    assert abs(p.central - 40.0 * (1 + mid) ** 1.5) < 1e-9


def test_below_the_anchor_ceiling_warming_raises_it_at_the_ceiling_it_cannot():
    ceil = anchor_ceiling()
    assert ceil is not None and damage_anchored_score(ceil) == damage_anchored_score(100.0)
    assert damage_anchored_score(project_potential(30.0, _delta(3.0)).central) > damage_anchored_score(30.0)
    assert damage_anchored_score(project_potential(ceil, _delta(3.0)).central) == damage_anchored_score(ceil)


@pytest.mark.skipif(not os.path.exists(GLOBAL_NPZ), reason="CMIP6 global delta field not built")
def test_on_the_real_cmip6_field_the_hot_house_path_never_falls():
    for lat, lon in ((40.42, -3.70), (37.39, -5.98), (48.14, 11.58), (45.46, 9.19), (35.47, -97.52), (-23.55, -46.63)):
        v = point._potential(lat, lon)
        if v is None:
            continue
        path = [damage_anchored_score(v)] + [
            damage_anchored_score(project_potential(v, cmip6_delta_latlon(lat, lon, "hot_house_3_5c", h)).central)
            for h in ("2030", "2050", "2100")]
        assert path == sorted(path), (lat, lon, path)


def test_posture_registry_matches_the_engine():
    item = next(it for it in projection_coverage()["items"] if it["hazard"] == "severe_convective")
    lo, _, hi = cape_rates()
    assert item["projects"] is True and item["band"] is True and item["mode"] == "cmip6_environment"
    assert f"~{lo*100:.0f}–{hi*100:.0f}%/°C" in item["mechanism"]
    assert item["gaps"] == reference()["not_projected"]
    # the scorer really runs this projection, under a version that retired the flat rows
    assert point.project_potential is project_potential and point.cmip6_delta_latlon is cmip6_delta_latlon
    assert point.MODEL_VERSION == "severe-convective-spc-anchored-v3"
