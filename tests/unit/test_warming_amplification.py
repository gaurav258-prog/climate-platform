"""Regional warming amplification (AR6-grounded, parametric v1).

The projection upgrade: the scenario deltas are GLOBAL-MEAN warming, but assets sit on land, which
warms faster than the mean, more so toward the poles. These tests pin the physically-required
properties of that correction — not exact coefficients (those are tunable), but the invariants a
regulated reviewer would insist on.
"""
from ml.scoring.heat_climatology import (
    warming_amplification, warming_delta, LAND_BASE, AMP_MAX,
)
from ml.scoring.drought_climatology import drought_score
from ml.scoring.heat_climatology import heat_score


def test_land_floor_and_none_default():
    # Unknown latitude falls back to the land-mean floor — still above the raw global mean (1.0).
    assert warming_amplification(None) == LAND_BASE
    assert LAND_BASE > 1.0


def test_amplification_rises_toward_poles():
    # Monotone in |latitude|: a Mediterranean belt warms more than the tropics, the Arctic more still.
    tropics, med, n_europe, arctic = (warming_amplification(x) for x in (5, 37, 52, 70))
    assert tropics < med < n_europe < arctic


def test_symmetric_in_hemisphere():
    assert warming_amplification(-42) == warming_amplification(42)


def test_capped():
    assert warming_amplification(89) <= AMP_MAX
    assert warming_amplification(90) <= AMP_MAX


def test_current_horizon_is_never_amplified():
    # The lane invariant: amplification only touches FORWARD projections. A live (current) score
    # must be identical regardless of latitude, because the warming delta is zero.
    for lat in (None, 0, 38, 65):
        assert warming_delta("hot_house_3_5c", "current", lat) == 0.0


def test_forward_delta_scales_with_latitude():
    # Same scenario+horizon, higher latitude → larger local warming than the global-mean-only case.
    glob = warming_delta("hot_house_3_5c", "2100", None)          # land-mean floor
    med = warming_delta("hot_house_3_5c", "2100", 38)
    assert med > glob > 0


def test_drought_projection_worsens_more_at_higher_latitude():
    # A drier future: the same SPEI under the same scenario scores a HIGHER drought hazard for a
    # higher-latitude cell, because its warming (hence evaporative drying) is amplified more.
    spei = -0.5
    low = drought_score(spei, "hot_house_3_5c", "2100", lat=10)
    high = drought_score(spei, "hot_house_3_5c", "2100", lat=55)
    assert high >= low


def test_heat_current_score_latitude_independent():
    # Belt-and-braces at the score level: current heat score doesn't move with latitude.
    a = heat_score(28.0, 26.0, 2.0, scenario="hot_house_3_5c", horizon="current", lat=10)
    b = heat_score(28.0, 26.0, 2.0, scenario="hot_house_3_5c", horizon="current", lat=60)
    assert a == b
