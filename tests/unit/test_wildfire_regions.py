from __future__ import annotations

import numpy as np

from services.validation.validators import wildfire_regions as W


def test_cell_index_roundtrip_and_wrap():
    i, j = W.cell_index([0.1, -89.9, 89.9], [0.1, -179.9, 190.0])
    assert (i[0], j[0]) == (180, 360)
    assert (i[1], j[1]) == (0, 0)
    assert j[2] == 20 and i[2] == 359          # 190E wraps to -170
    la, lo = W.cell_centre(180, 360)
    assert (la, lo) == (0.25, 0.25)


def test_cell_area_equator_and_pole():
    eq = float(W.cell_area_ha(180))
    assert 3.0e5 < eq < 3.2e5                    # ~55.6 km x 55.6 km = ~3.09e5 ha
    assert float(W.cell_area_ha(359)) < eq * 0.05


def test_aggregate_points_sums_and_skips_bad():
    out = W.aggregate_points([0.1, 0.2, 5.0], [0.1, 0.2, 5.0], [10.0, 5.0, float("nan")])
    assert out == {(180, 360): 15.0}


def test_aggregate_grid_conserves_area():
    lat = np.array([0.125, 0.375]); lon = np.array([0.125, 0.375])
    g = W.aggregate_grid(np.full((2, 2), 1e4), lat, lon)
    assert g.sum() == 4.0 and g[180, 360] == 4.0


def test_burned_fraction_clips():
    assert W.burned_fraction(50, 100) == 0.5 and W.burned_fraction(500, 100) == 1.0 and W.burned_fraction(1, 0) == 0.0


def test_auc_occurrence():
    assert W.auc_occurrence([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0
    assert W.auc_occurrence([1, 2], [0, 0]) is None
