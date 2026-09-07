"""Wildfire hazard climatology: pure formula, no DB / no grids."""
import numpy as np

from ml.scoring.wildfire_climatology import H_SCALE_FRAC, VARIANTS, W_SCALE_DAYS, wildfire_hazard


def test_terms_are_monotone_and_bounded():
    days = np.array([0, 5, 15, 45, 120]); r = wildfire_hazard(days, 1.0, 0.0)
    w = r["weather_term"]; assert (np.diff(w) > 0).all() and w[0] == 0 and w[-1] < 100
    assert abs(w[2] - 63.2) < 0.5           # one scale (15 days) → 1 - e^-1
    h = wildfire_hazard(0, 1.0, np.array([0, 0.02, 0.2]))["history_term"]
    assert h[0] == 0 and abs(h[1] - 63.2) < 0.5 and h[2] > 99
    assert W_SCALE_DAYS == 15.0 and H_SCALE_FRAC == 0.02


def test_no_fuel_means_no_weather_driven_hazard():
    assert wildfire_hazard(120, 0.0, 0.0, "weather_fuel")["score"] == 0.0
    assert wildfire_hazard(120, 1.0, 0.0, "weather_fuel")["score"] > 99


def test_variants_differ_only_by_history():
    a = wildfire_hazard(15, 1.0, 0.0, "weather_fuel")["score"]
    b = wildfire_hazard(15, 1.0, 0.0, "with_history")["score"]
    c = wildfire_hazard(15, 1.0, 0.05, "with_history")["score"]
    assert abs(b - 0.6 * a) < 1e-9 and c > b
    assert set(VARIANTS) == {"weather_fuel", "with_history"}
