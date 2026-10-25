"""The official building share (the product owner's decisions of 2026-10-25): Spain by province from the Catastro's
construction over total cadastral value, Germany nationally from Eurostat's household balance sheet — a lower bound —
and nowhere else; used by the loss engine only for an organisation that adopts it, only for a bank's or a property
trust's book that states no building value."""
from __future__ import annotations

from services.loss.stated_values import with_building_share
from services.reference.building_share import share_at, table

ADOPTED = {"loss_building_share": "official_statistics"}


def test_each_spanish_region_takes_its_own_provinces_share_e337():
    """E337: a region was matched to every province one of its postcodes touches, so Barcelona (ES511) took Tarragona's
    share. Each region now takes the province most of its own postcodes begin with."""
    t = table()["by_nuts3"]
    assert t["ES511"]["area"] == "Barcelona" and t["ES514"]["area"] == "Tarragona" and t["ES300"]["area"] == "Madrid"
    assert all(v["postcodes_in_province"] >= 0.9 for v in t.values())
    assert all(0 < v["share"] < 1 for v in t.values())
    assert not {"ES211", "ES212", "ES213", "ES220"} & set(t)                # the foral cadastres are not in the file


def test_every_source_is_quoted_with_its_checksum():
    for s in table()["sources"]:
        assert s["url"].startswith("https://") and len(s["sha256"]) == 64 and s["licence"] and s["publisher"]
    de = table()["by_country"]["DE"]
    assert de["lower_bound"] is True and de["share"] == round(de["dwellings_meur"] / (de["dwellings_meur"] + de["land_meur"]), 4)


def test_a_place_takes_its_official_share_or_none():
    assert share_at("ES", 41.39, 2.16)["region"] == "ES511"                  # Barcelona
    assert share_at("DE", 48.8, 9.2)["lower_bound"] is True
    assert share_at("ES", 43.26, -2.93) is None                              # Bilbao: its own cadastre
    assert share_at("FR", 48.8, 2.3) is None


def _asset(**kw) -> dict:
    return {"asset_id": "a", "value": 1_000_000.0, "building_value": None, "asset_value": None, "country": "ES",
            "latitude": 41.39, "longitude": 2.16, **kw}


def test_the_stated_value_times_the_share_only_where_adopted_and_needed():
    es = table()["by_nuts3"]["ES511"]["share"]
    got = with_building_share([_asset()], "realestate", ADOPTED)[0]
    assert got["building_value"] == round(1_000_000 * es, 2) == got["asset_value"]
    assert got["value_basis"]["source"] == "es_catastro" and got["value_basis"]["stated_value_eur"] == 1_000_000
    de = with_building_share([_asset(country="DE", latitude=48.8, longitude=9.2)], "banking", ADOPTED)[0]
    assert de["value_basis"]["lower_bound"] is True
    kept = [_asset(building_value=300_000.0), _asset(country="ES", latitude=43.26, longitude=-2.93), _asset(position=True)]
    assert [a.get("value_basis") for a in with_building_share(kept, "banking", ADOPTED)] == [None, None, None]
    assert "value_basis" not in with_building_share([_asset()], "realestate", {})[0]           # not adopted: the gap stays
    assert "value_basis" not in with_building_share([_asset()], "insurance", ADOPTED)[0]       # an insured value is not split
