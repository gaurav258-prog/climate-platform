"""Every drawn cell comes from one service; it is clipped only where the coastline is finer than the cell."""
import h3
import pytest
from shapely.geometry import Polygon, shape

from services.geo.cells import COUNTRIES_PATH, cell_shape, clips_at, country_of

needs_land = pytest.mark.skipif(not COUNTRIES_PATH.exists(), reason="country boundaries not fetched")


def _full(cell):
    return Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(cell)])


def test_clipping_resolution_follows_the_layer_accuracy():
    assert clips_at(4) and clips_at(5)          # 22 km / 8.5 km edges against a 1.5 km coastline
    assert not clips_at(7) and not clips_at(8)  # 1.2 km / 0.46 km edges: the coastline is the error


@needs_land
def test_coarse_coastal_cells_are_clipped_and_named():
    coast = cell_shape(h3.latlng_to_cell(25.77, -80.19, 4))     # Miami Beach, res-4
    got, full = shape(coast["geometry"]), _full(coast["cell"])
    assert coast["clipped"] and coast["on_land"] and coast["country"] == "US"
    assert 0 < got.area < full.area * 0.98 and full.buffer(1e-9).covers(got)
    assert coast["rings_latlon"][0][0][0] == pytest.approx(coast["rings_lonlat"][0][0][1])
    inland = cell_shape(h3.latlng_to_cell(39.74, -104.99, 4))   # Denver: nothing to cut
    assert not inland["clipped"] and inland["on_land"] and shape(inland["geometry"]).equals(_full(inland["cell"]))


@needs_land
def test_fine_coastal_cells_are_drawn_whole_and_only_open_sea_is_flagged():
    for lat, lon in [(25.77, -80.19), (18.4655, -66.1057), (38.72031, -9.12661)]:   # Miami Beach, San Juan, Lisbon riverside
        c = cell_shape(h3.latlng_to_cell(lat, lon, 8))
        assert not c["clipped"] and c["on_land"] and c["country"] in ("US", "PR", "PT"), (lat, lon, c["country"])
        assert shape(c["geometry"]).equals(_full(c["cell"]))
    sea = cell_shape(h3.latlng_to_cell(30.0, -40.0, 8))         # mid-Atlantic
    assert not sea["on_land"] and sea["country"] is None


@needs_land
def test_country_lookup_comes_from_the_same_layer():
    assert country_of(48.86, 2.35) == "FR" and country_of(30.0, -40.0) is None
