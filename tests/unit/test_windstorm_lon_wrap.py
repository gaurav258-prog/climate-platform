"""The global gust grid runs 0-359.5°E; a western-hemisphere point must read its own column, not the lon-0 one."""
import pytest

from ml.scoring import windstorm_point as W


def test_negative_and_360_longitudes_hit_the_same_cell():
    if W._field() is None:
        pytest.skip("windstorm climatology not built")
    for lat, lon in [(39.7, -105.0), (35.2, -101.7), (40.7, -74.0), (-33.9, -70.7)]:
        assert W._gust(lat, lon) == W._gust(lat, lon + 360.0)


def test_dateline_wraps():
    if W._field() is None:
        pytest.skip("windstorm climatology not built")
    assert W._gust(0.0, 179.9) is not None and W._gust(0.0, -179.9) is not None
