"""The region borders (services.reference.region_shapes): a place belongs to the one region whose polygon contains it;
every code is one the region reference knows, with its publisher's name. Needs the Natural Earth file on disk."""
from __future__ import annotations

import pytest

from services.reference import region_shapes as R
from services.reference import regions

pytestmark = pytest.mark.skipif(not (R.ROOT / R.reference()["iso3166_2"]["file"]).exists(),
                                reason="the Natural Earth admin-1 file is not fetched on this machine")


@pytest.mark.parametrize("lat,lon,code", [(38.5, -98.5, "US-KS"), (52.1, -106.6, "CA-SK"), (-29.7, -53.8, "BR-RS"),
                                          (39.6, -3.0, "ES42"), (41.6, -0.9, "ES24"), (35.1, 33.4, "CY00"),
                                          (5.6, -0.2, None), (30.0, -40.0, None)])
def test_a_place_belongs_to_the_region_that_contains_it(lat, lon, code):
    assert R.region_of(lat, lon) == code


def test_every_region_is_a_code_of_the_reference_with_its_publishers_name():
    codes = set(R.shapes())
    assert all(regions.known(c) for c in codes)
    assert {c for c in codes if "-" in c[:3]} <= {k for cc in R.reference()["iso3166_2"]["countries"]
                                                   for k in regions.of_country(cc)}
    assert not any("~" in c for c in codes)                       # Natural Earth placeholders are never codes
    assert regions.name("ES42") == "Castilla-La Mancha" and regions.name("US-KS") == "Kansas"
    assert R.country_of("EL30") == "GR" and R.country_of("US-KS") == "US" and R.country_of("ES42") == "ES"
    assert R.scheme_of("US") == "iso3166_2" and R.scheme_of("ES") == "nuts2" and R.scheme_of("AR") is None
