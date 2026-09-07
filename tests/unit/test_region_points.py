import pytest

from services.geo.region_points import NUTS3_PATH, TERCET_DIR, nuts3_point, resolve
from services.geo.regions import region_for

needs_nuts = pytest.mark.skipif(not NUTS3_PATH.exists(), reason="NUTS-3 boundaries not fetched")


@needs_nuts
def test_nuts3_point_lies_inside_its_region_and_is_labelled():
    p = nuts3_point("DE254")
    assert p["country"] == "DE" and p["location_precision"] == "nuts3" and p["name"].startswith("Nürnberg")
    assert region_for(p["lat"], p["lon"])["key"] == "DE254"


@needs_nuts
def test_country_only_is_unlocated_never_fabricated():
    assert resolve("ES") is None and resolve(None) is None and nuts3_point("XX999") is None


@needs_nuts
@pytest.mark.skipif(not (TERCET_DIR / "pc2020_ES_NUTS-2021.csv").exists(), reason="TERCET ES table not fetched")
def test_spanish_postcode_resolves_via_tercet():
    p = resolve("ES", postcode="26001")
    assert p and p["nuts3"] == "ES230" and p["location_precision"] == "postcode→nuts3"
