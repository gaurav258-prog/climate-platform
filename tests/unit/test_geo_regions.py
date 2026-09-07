"""Regional aggregation for the supervisor heat map: NUTS-3 inside the EU, H3 res-4 hexagons elsewhere."""
import pytest

from services.geo.regions import NUTS3_PATH, aggregate_by_region, region_for

needs_nuts = pytest.mark.skipif(not NUTS3_PATH.exists(), reason="NUTS-3 boundaries not fetched")


@needs_nuts
def test_eu_points_resolve_to_nuts3_and_others_to_h3():
    nue = region_for(49.45, 11.08); nap = region_for(40.85, 14.27); accra = region_for(5.6, -0.2)
    assert nue["kind"] == "nuts3" and nue["key"] == "DE254" and nue["country"] == "DE"
    assert nap["kind"] == "nuts3" and nap["key"].startswith("ITF3")
    assert accra["kind"] == "h3" and accra["geometry"]["type"] == "Polygon" and len(accra["key"]) == 15


@needs_nuts
def test_aggregate_rolls_up_without_exposing_sites():
    pts = [{"lat": 49.45, "lon": 11.08, "value_eur": 10.0, "score": 80.0, "hazard": "flood", "entity": "A"},
           {"lat": 49.46, "lon": 11.09, "value_eur": 5.0, "score": 20.0, "hazard": "drought", "entity": "B"},
           {"lat": 5.6, "lon": -0.2, "value_eur": 1.0, "score": None, "hazard": None, "entity": "A"}]
    regs = aggregate_by_region(pts)
    assert [r["key"] for r in regs][0] == "DE254"
    de = regs[0]
    assert de["n_sites"] == 2 and de["value_eur"] == 15 and de["max_score"] == 80.0 and de["worst_hazard"] == "flood"
    assert de["mean_score"] == 50.0 and de["entities"] == ["A", "B"]
    assert all("lat" not in r and "lon" not in r and "sites" not in r for r in regs)   # no site leaks through
    gh = next(r for r in regs if r["kind"] == "h3"); assert gh["max_score"] is None and gh["mean_score"] is None
