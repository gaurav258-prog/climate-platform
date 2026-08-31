"""Phase-1 channels (landslide, temperature/precipitation variability) — pure calibration, offline."""
from __future__ import annotations

from core.types import HazardType, normalize_hazard
from ml.scoring.climate_change_point import changing_precip_score as cps
from ml.scoring.climate_change_point import changing_temp_score as cts
from ml.scoring.climate_variability_point import precip_variability_score as pv
from ml.scoring.climate_variability_point import temp_variability_score as tv
from ml.scoring.landslide_point import CLASS_SCORE


def test_landslide_class_map_monotonic():
    scores = [CLASS_SCORE[c] for c in range(6)]
    assert scores == sorted(scores)
    assert CLASS_SCORE[0] < 10 and CLASS_SCORE[5] >= 90


def test_temp_variability_monotonic_and_banded():
    assert tv(2, 1) < tv(10, 1) < tv(25, 1) < tv(40, 1)
    assert tv(2, 0) < 20        # equatorial — small seasonal swing
    assert tv(55, 1) >= 95      # extreme continental (Siberia)


def test_precip_variability_monsoon_high_even_low():
    assert pv(0.2, 0.2, 3.0) < pv(1.2, 0.3, 3.0)   # even rainfall < monsoon
    assert pv(1.2, 0.3, 3.0) >= 80                  # strongly seasonal (monsoon)


def test_precip_variability_desert_damped():
    """A near-zero-rain desert must not be lifted to 'high variability' by noise."""
    assert pv(1.5, 0.3, 0.05) < 15


def test_bounded():
    for f, args in [(tv, (200, 50)), (tv, (0, 0)), (pv, (5, 5, 10)), (pv, (0, 0, 0))]:
        assert 0.0 <= f(*args) <= 100.0


def test_changing_temp_monotonic_banded():
    assert cts(1) < cts(2) < cts(3.5) < cts(5)
    assert 45 <= cts(2) <= 55        # +2°C ≈ 50
    assert cts(5) >= 80


def test_changing_precip_symmetric_in_magnitude():
    assert cps(0.5) == cps(-0.5)     # drying and wetting equally hazardous
    assert 45 <= cps(0.25) <= 55     # ±25% ≈ 50


def test_hazard_types_registered():
    for v in ("landslide", "temp_variability", "precip_variability", "changing_temp", "changing_precip"):
        assert v in {h.value for h in HazardType}
    assert normalize_hazard("temperature variability") is HazardType.TEMP_VARIABILITY
    assert normalize_hazard("hydrological_variability") is HazardType.PRECIP_VARIABILITY
    assert normalize_hazard("slope failure") is HazardType.LANDSLIDE
    assert normalize_hazard("changing temperature") is HazardType.CHANGING_TEMP
