"""Heavy-precipitation Screening indicator — calibration must stay sensible (pure, offline)."""
from __future__ import annotations

from core.types import HazardType, normalize_hazard
from ml.scoring.heavy_precip_climatology import heavy_precip_score as s


def test_calibration_anchors():
    """Real wettest-month mm/day anchors map to the intended bands (arid low → monsoon high)."""
    assert s(0.1, 0.15) < 5          # Sahara — negligible
    assert 8 <= s(2.2, 0.8) <= 22    # London temperate
    assert 60 <= s(20.7, 6.0) <= 85  # Mumbai monsoon
    assert s(35.4, 10.0) >= 88       # Cherrapunji — wettest on Earth
    assert s(111.0, 30.0) >= 99      # global extreme saturates near 100


def test_monotonic_in_precipitation():
    xs = [0.1, 2, 5, 10, 20, 35, 60, 111]
    scores = [s(x) for x in xs]
    assert all(a <= b for a, b in zip(scores, scores[1:]))


def test_warming_raises_score():
    """Clausius–Clapeyron: a warmer scenario/horizon intensifies extreme rainfall → higher score."""
    assert s(20.7, 6.0, "hot_house_3_5c", "2100") > s(20.7, 6.0, "baseline", "current")


def test_arid_not_inflated_by_noise():
    """A bone-dry cell with a noisy near-zero std must not be lifted by the variability bump."""
    assert s(0.1, 0.5) < 5


def test_bounded_and_zero_safe():
    assert 0.0 <= s(0.0, 0.0) <= 100.0
    assert 0.0 <= s(500.0, 200.0) <= 100.0


def test_hazard_type_registered():
    assert HazardType.HEAVY_PRECIP.value == "heavy_precip"
    assert normalize_hazard("heavy precipitation") is HazardType.HEAVY_PRECIP
    assert normalize_hazard("extreme_rainfall") is HazardType.HEAVY_PRECIP
