"""Regional warming amplification (AR6-grounded, parametric v1).

The projection upgrade: the scenario deltas are GLOBAL-MEAN warming, but assets sit on land, which
warms faster than the mean, more so toward the poles. These tests pin the physically-required
properties of that correction — not exact coefficients (those are tunable), but the invariants a
regulated reviewer would insist on.
"""
from ml.scoring.heat_climatology import (
    warming_amplification, warming_delta, LAND_BASE, AMP_MAX, precip_drying_spei,
)
from ml.scoring.drought_climatology import drought_score
from ml.scoring.heat_climatology import heat_score, heat_anomaly_score


def test_heat_anomaly_score_mirrors_drought_score():
    """The crop-fit heat driver is Φ(+z)×100, the exact mirror of drought_score's Φ(−SPEI)×100:
    a normal season reads ~50, one σ hotter ~84, two σ ~98; monotone in z; None → 0; and a season
    z σ hot equals a season z σ dry in drought terms (same percentile, opposite tail)."""
    assert heat_anomaly_score(None) == 0.0
    assert heat_anomaly_score(0.0) == 50.0
    assert 83 < heat_anomaly_score(1.0) < 85
    assert 97 < heat_anomaly_score(2.0) < 99
    assert heat_anomaly_score(2.0) > heat_anomaly_score(1.0) > heat_anomaly_score(0.0)
    # symmetry of the two hazard percentiles: hot z ≡ dry SPEI=−z
    assert abs(heat_anomaly_score(1.3) - drought_score(-1.3)) < 0.2


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


# --- AR6 Mediterranean precipitation decline (projections v2) ----------------------------------

def test_precip_drying_only_in_mediterranean():
    # Robust AR6 signal is applied inside the Med box (Spain olive) and nowhere we can't cite it.
    med = precip_drying_spei("hot_house_3_5c", "2100", lat=38, lon=-4)      # Andalusia
    iran = precip_drying_spei("hot_house_3_5c", "2100", lat=36, lon=47)     # Zagros — east of the box
    cocoa = precip_drying_spei("hot_house_3_5c", "2100", lat=6, lon=-5)     # tropics
    assert med > 0
    assert iran == 0.0 and cocoa == 0.0


def test_precip_drying_zero_at_current_and_without_coords():
    assert precip_drying_spei("hot_house_3_5c", "current", lat=38, lon=-4) == 0.0
    assert precip_drying_spei("hot_house_3_5c", "2100", lat=None, lon=None) == 0.0
    assert precip_drying_spei("hot_house_3_5c", "2100", lat=38, lon=None) == 0.0


def test_precip_drying_scales_with_warming():
    a = precip_drying_spei("orderly_1_5c", "2100", lat=38, lon=-4)
    b = precip_drying_spei("hot_house_3_5c", "2100", lat=38, lon=-4)
    assert b > a > 0


def test_med_drought_projection_exceeds_temperature_only():
    # A Med cell's forward drought score must be at least as high WITH the precip term as a cell
    # outside the Med box at the same latitude/SPEI (which gets temperature-only drying).
    spei = -0.3
    med = drought_score(spei, "hot_house_3_5c", "2100", lat=38, lon=-4)     # in Med box
    non_med = drought_score(spei, "hot_house_3_5c", "2100", lat=38, lon=100)  # same lat, outside box
    assert med >= non_med
