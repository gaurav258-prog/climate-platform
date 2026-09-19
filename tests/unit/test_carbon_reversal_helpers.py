from __future__ import annotations

import numpy as np

from services.validation.validators.carbon_reversal import (by_stratum, carb_agreement, loss_counts, safe_spearman,
                                                            tile_name, tiles_for_bounds)


def test_tile_name():
    assert tile_name(-3.2, -62.5) == "00N_070W"
    assert tile_name(5.0, 15.0) == "10N_010E"
    assert tile_name(-5.0, -55.0) == "00N_060W"
    assert tile_name(-15.0, -45.0) == "10S_050W"


def test_tiles_for_bounds():
    assert tiles_for_bounds(11, 1, 19, 9) == ["10N_010E"]
    assert len(tiles_for_bounds(9, 1, 11, 9)) == 2


def test_loss_counts():
    ly = np.array([[0, 21, 24], [25, 20, 22]])
    m = np.array([[1, 1, 1], [1, 1, 0]])
    assert loss_counts(ly, m) == (2, 5)


def test_spearman_and_strata():
    assert safe_spearman([1, 2, 3], [1, 2, 3]) == 1.0
    assert safe_spearman([1, 1, 1], [1, 2, 3]) is None
    r = by_stratum(list(range(12)), list(range(12)), ["a"] * 12 + [])
    assert r["a"]["rho"] == 1.0
    assert by_stratum([1, 2], [1, 2], ["b", "b"])["b"]["rho"] is None


def test_carb_agreement():
    a = carb_agreement([10, 20, 30, 40], [0.01, 0.02, 0.02, 0.04])
    assert a["spearman"] > 0.8 and a["n_by_rating"]["0.02"] == 2
