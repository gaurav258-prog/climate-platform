"""Physically-grounded flood/storm/wildfire projection — documented sensitivities + honest band."""
from ml.scoring.cmip6 import Cmip6Delta
from ml.scoring.physical_projection import SENSITIVITY, project


def _d(dtas=2.0, dpr=-0.1, n=4, dtas_std=0.5, dpr_std=0.05):
    return Cmip6Delta(dtas, dpr, n, dtas_std, dpr_std)


def test_flood_uses_clausius_clapeyron_warming_only():
    # 7%/°C × 2°C = +14% on the base score; precip has no weight for flood
    sc, lo, hi = project(50.0, "flood", _d(dtas=2.0, dpr=-0.5))
    assert sc == round(50.0 * 1.14, 2)          # precip change ignored
    assert lo is not None and lo < sc < hi      # band from the ±1σ warming spread


def test_storm_scales_5pct_per_degree():
    sc, _, _ = project(40.0, "storm", _d(dtas=3.0, dpr=0.0, dtas_std=0.0, dpr_std=0.0))
    assert sc == round(40.0 * (1 + 0.05 * 3.0), 2)   # 15% uplift


def test_wildfire_rises_with_warming_and_drying():
    hotter_drier = project(30.0, "wildfire", _d(dtas=3.0, dpr=-0.2))[0]
    milder = project(30.0, "wildfire", _d(dtas=1.0, dpr=0.0))[0]
    assert hotter_drier > milder                # drying (dpr<0) and warming both raise fire hazard


def test_score_capped_at_100():
    sc, lo, hi = project(95.0, "storm", _d(dtas=5.0, dtas_std=1.0))
    assert sc <= 100.0 and (hi is None or hi <= 100.0)


def test_no_band_without_coverage_or_spread():
    assert project(50.0, "flood", None) == (50.0, None, None)          # no CMIP6 coverage
    assert project(50.0, "flood", _d(n=1, dtas_std=0, dpr_std=0))[1] is None  # single model → no band


def test_non_climate_hazard_is_not_projected():
    assert project(50.0, "seismic", _d()) == (50.0, None, None)        # geophysical, no climate uplift
    assert "seismic" not in SENSITIVITY
