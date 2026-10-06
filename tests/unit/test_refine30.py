"""E171/E172: the 30 m refinement re-spreads the mapped water over the terrain by the protocol's stated method, and
reads the 90 m maps exactly as the validator does."""
from __future__ import annotations

import numpy as np
import pytest

from services.loss.refine30 import respread


def test_water_settles_to_the_surface_of_its_90m_pixel():
    # one wet 90 m pixel, three sub-pixels at 10, 11, 12 m, mapped depth 1 m → surface 12 m → 2 m, 1 m, dry
    got = respread(np.array([7, 7, 7]), np.array([10.0, 11.0, 12.0]), np.array([1.0, 1.0, 1.0]))
    assert sorted(got.tolist()) == [1.0, 2.0]


def test_each_90m_pixel_keeps_its_own_surface():
    got = respread(np.array([1, 1, 2, 2]), np.array([0.0, 2.0, 100.0, 100.0]), np.array([0.5, 0.5, 0.3, 0.3]))
    assert sorted(np.round(got, 6).tolist()) == [0.3, 0.3, 1.5]      # pixel 1: surface 1.5; pixel 2: flat, 0.3 m


def test_nothing_wet_gives_nothing():
    assert respread(np.array([], dtype=int), np.array([]), np.array([])).size == 0


def test_the_90m_reading_is_the_validators(monkeypatch):
    from shapely.geometry import box

    from ml.scoring.flood_jrc import TileSet
    from services.loss.refine30 import box_stats, dem_paths
    b = box(11.9, 44.4, 12.0, 44.5)                                   # Emilia-Romagna, inside a test tile
    if dem_paths(*b.bounds) is None or TileSet().stats(b) is None:
        pytest.skip("the flood maps or the terrain tiles are not on this machine")
    st, ref = box_stats(b), TileSet().stats(b)
    assert st["m90"][0] == pytest.approx(ref[100][0]) and st["m90"][1] == pytest.approx(ref[100][1])
