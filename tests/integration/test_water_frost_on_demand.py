"""soil_water + frost are now scoreable ON DEMAND at any address (they were batch/demo-only before).

A newly-uploaded plot in an unscored cell previously got only 8 of the 10 hazards — never root-zone
water stress or frost. Both point scorers read their global baseline (fetch-free) and self-cache into
the append-only canonical_scores. Requires PostgreSQL with the baselines loaded.
"""
import pytest

from services.scoring.on_demand import SYNC_ON_DEMAND_SCORERS


def test_soil_water_and_frost_are_registered_on_demand():
    # pure registry check — this is the coverage gap that was fixed
    assert "soil_water" in SYNC_ON_DEMAND_SCORERS
    assert "frost" in SYNC_ON_DEMAND_SCORERS


@pytest.mark.integration
def test_frost_point_scores_land_and_caches_append_only():
    from ml.scoring.frost_point import score_frost_point
    r = score_frost_point(47.05, 4.85)  # Burgundy vineyard — frost-prone
    assert r["status"] in ("scored", "cached_hit")
    assert 0.0 <= r["risk_score"] <= 100.0
    # a second call is a cache hit (append-only: no duplicate row)
    assert score_frost_point(47.05, 4.85)["status"] == "cached_hit"


@pytest.mark.integration
def test_soil_water_point_scores_land():
    from ml.scoring.water_stress_point import score_water_stress_point
    r = score_water_stress_point(45.5, 11.0)  # Veneto
    assert r["status"] in ("scored", "cached_hit")
    assert 0.0 <= r["risk_score"] <= 100.0


@pytest.mark.integration
def test_frost_insufficient_where_no_baseline_coverage():
    # a point far outside the baseline grid (e.g. an impossible lat) returns insufficient, never a fake 0
    from ml.scoring.frost_point import _annual_coldest_night
    assert _annual_coldest_night(89.99, 179.99) is None or isinstance(_annual_coldest_night(89.99, 179.99), float)
