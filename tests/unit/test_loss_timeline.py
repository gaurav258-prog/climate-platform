"""Blending flood between two maps by warming (services.loss.engine._blend; the product owner's decision of 2026-10-22):
the water depth is blended, a dry pixel's depth being none, and the pixel is wet where the blend is above the source's
dry level."""
from __future__ import annotations

import pytest

from services.loss.engine import _blend


def _map(**depths):
    return {int(rp): {"status": "sampled", "cell_fraction": 1.0 if d > 0 else 0.0, "cell_mean": d} for rp, d in depths.items()}


def test_wet_maps_blend_their_depths():
    out = _blend(_map(**{"100": 1.0}), _map(**{"100": 2.0}), 0.25, 0.0)
    assert out[100] == {"status": "sampled", "cell_fraction": 1.0, "cell_mean": pytest.approx(1.25)}


def test_a_dry_map_is_depth_none_and_the_blend_is_wet_where_water_remains():
    out = _blend(_map(**{"10": 0.0, "100": 0.0}), _map(**{"10": 0.0, "100": 2.0}), 0.1, 0.0)
    assert out[10]["cell_fraction"] == 0.0 and out[10]["cell_mean"] == 0.0
    assert out[100]["cell_fraction"] == 1.0 and out[100]["cell_mean"] == pytest.approx(0.2)


def test_weight_zero_is_the_lower_map_and_one_the_upper():
    lo, hi = _map(**{"100": 0.5}), _map(**{"100": 1.5})
    assert _blend(lo, hi, 0.0, 0.0)[100]["cell_mean"] == 0.5 and _blend(lo, hi, 1.0, 0.0)[100]["cell_mean"] == 1.5
