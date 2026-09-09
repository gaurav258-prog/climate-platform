"""Shared GEOS indexes are used from the API thread pool: concurrent lookups must be safe and consistent."""
import threading

import pytest

from services.geo.cells import COUNTRIES_PATH, cell_shape, country_of
from services.geo.regions import region_for

needs_land = pytest.mark.skipif(not COUNTRIES_PATH.exists(), reason="country boundaries not fetched")


@needs_land
def test_concurrent_lookups_are_consistent():
    pts = [(48.86, 2.35), (25.77, -80.19), (38.72, -9.13), (52.52, 13.40), (41.39, 2.17), (59.33, 18.07)]
    expected = [(country_of(la, lo), region_for(la, lo)["key"], cell_shape(__import__("h3").latlng_to_cell(la, lo, 5))["country"]) for la, lo in pts]
    out, errors = [], []

    def work():
        try:
            for _ in range(20):
                got = [(country_of(la, lo), region_for(la, lo)["key"], cell_shape(__import__("h3").latlng_to_cell(la, lo, 5))["country"]) for la, lo in pts]
                out.append(got == expected)
        except Exception as e:
            errors.append(repr(e))
    ts = [threading.Thread(target=work) for _ in range(12)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert not errors and out and all(out)
