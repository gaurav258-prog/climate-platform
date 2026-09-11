"""Pure-logic tests for the GRACE water-stress backtest (no network, no DB)."""
from __future__ import annotations

import numpy as np

from scripts.fetch_grace_trends import decimal_years, ols_trends
from services.validation.validators.water_stress_grace import (
    EXCLUSION_BOXES,
    decline_rate,
    excluded_by,
    on_lattice,
    select_cells,
)


def test_ols_trend_recovers_known_slope_with_gaps():
    t = np.linspace(2002.3, 2026.2, 255)
    y = np.stack([2.0 * t - 4000.0, -0.5 * t + 1000.0], axis=1)
    y[10:40, 1] = np.nan                      # a GRACE→GRACE-FO gap in one column
    slope, n = ols_trends(y, t, min_months=150)
    assert np.allclose(slope, [2.0, -0.5], atol=1e-6)
    assert n[0] == 255 and n[1] == 225


def test_ols_trend_is_nan_below_min_months():
    t = np.linspace(2002.3, 2026.2, 255)
    y = np.full((255, 1), np.nan)
    y[:100, 0] = t[:100]
    slope, n = ols_trends(y, t, min_months=150)
    assert np.isnan(slope[0]) and n[0] == 100


def test_decimal_years_mid_year():
    dy = decimal_years(np.array(["2002-01-01", "2002-07-02", "2026-03-17"], dtype="datetime64[D]"))
    assert dy[0] == 2002.0
    assert abs(dy[1] - 2002.5) < 0.01
    assert 2026.2 < dy[2] < 2026.22


def test_decline_rate_flips_sign():
    assert decline_rate(-1.5) == 1.5      # storage falling 1.5 cm/yr → hazard positive
    assert decline_rate(0.7) == -0.7


def test_exclusions_hit_ice_and_gia_regions_only():
    assert excluded_by(-75.0, 20.0) == "antarctica"
    assert excluded_by(70.5, -40.0) == "greenland"
    assert excluded_by(62.0, 20.0) == "fennoscandia_gia"
    assert excluded_by(58.0, -85.0) == "hudson_bay_laurentide_gia"
    assert excluded_by(34.0, 88.0) == "tibetan_plateau"
    assert excluded_by(35.5, 75.5) == "karakoram_west_himalaya"
    # the big pumping/drought signals the test is about are NOT excluded
    assert excluded_by(29.25, 76.25) is None       # NW India aquifer
    assert excluded_by(36.25, -119.75) is None     # Central Valley
    assert excluded_by(40.25, -3.75) is None       # Iberia
    assert all(len(b) == 5 for b in EXCLUSION_BOXES)


def test_lattice_keeps_every_second_node_at_2deg():
    assert on_lattice(-89.75, -179.75, 2.0)
    assert not on_lattice(-88.75, -179.75, 2.0)
    assert not on_lattice(-89.75, -178.75, 2.0)
    assert on_lattice(0.25, 0.25, 2.0)
    assert on_lattice(0.25, 0.25, 1.0) and on_lattice(1.25, 0.25, 1.0)


def test_select_cells_applies_lattice_and_exclusions():
    rows = [
        {"lat": 0.25, "lon": 0.25, "trend_cm_yr": -2.0, "n_months": 255},      # kept, obs +2.0
        {"lat": 1.25, "lon": 0.25, "trend_cm_yr": -9.0, "n_months": 255},      # off the 2° lattice
        {"lat": -80.25, "lon": 0.25, "trend_cm_yr": -9.0, "n_months": 255},    # antarctica
        {"lat": 60.25, "lon": 20.25, "trend_cm_yr": 1.0, "n_months": 255},     # fennoscandia
    ]
    kept, counts = select_cells(rows, 2.0)
    assert [c["obs"] for c in kept] == [2.0]
    assert kept[0]["h3_cell"].startswith("88")
    assert counts == {"antarctica": 1, "fennoscandia_gia": 1}
