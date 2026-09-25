"""Matching incoming records to the live book (services/intake/matching.py) and the sector build rules — pure, no DB."""
from __future__ import annotations

import pytest

from services.ingest.sector_contract import RowIssue
from services.ingest.sector_ingest import BANK, INSURANCE
from services.intake import mapping, matching

_KW = dict(name_field="entity_name", value_field="primary_value_eur", compare=("entity_name", "latitude", "longitude",
                                                                             "primary_value_eur", "external_ref", "region"))


def _live(eid, name="Depot A", lat=48.85, lon=2.35, value=1_000_000.0, ref=None, region="IDF"):
    return {"entity_id": eid, "entity_name": name, "latitude": lat, "longitude": lon, "primary_value_eur": value,
            "external_ref": ref, "region": region}


def _rec(name="Depot A", lat=48.85, lon=2.35, value=1_000_000.0, ref=None, region="IDF"):
    return {"entity_name": name, "latitude": lat, "longitude": lon, "primary_value_eur": value, "external_ref": ref, "region": region}


def test_same_id_is_the_same_asset_even_if_renamed():
    r = matching.match([_rec(name="Depot A (renamed)", ref="L-1")], [_live("e1", ref="L-1")], **_KW)[0]
    assert r["status"] == "update" and r["entity_id"] == "e1" and r["diff"]["entity_name"] == ["Depot A", "Depot A (renamed)"]


def test_identical_row_is_unchanged():
    assert matching.match([_rec(ref="L-1")], [_live("e1", ref="L-1")], **_KW)[0]["status"] == "unchanged"


def test_name_alone_never_matches():
    r = matching.match([_rec(lat=45.0, lon=5.0)], [_live("e1")], **_KW)[0]   # same name, ~500 km away
    assert r["status"] == "new"


def test_name_and_location_match_attaches_the_id():
    r = matching.match([_rec(ref="L-9")], [_live("e1")], **_KW)[0]
    assert r["status"] == "update" and r["attach_ref"] and r["diff"] == {"external_ref": [None, "L-9"]}


def test_two_live_candidates_is_ambiguous():
    r = matching.match([_rec()], [_live("e1"), _live("e2", lat=48.8501)], **_KW)[0]
    assert r["status"] == "ambiguous" and set(r["candidates"]) == {"e1", "e2"}


def test_a_different_id_is_a_different_asset():
    # the live asset already has its own id; a row with another id is not it, whatever the name
    assert matching.match([_rec(ref="L-2")], [_live("e1", ref="L-1")], **_KW)[0]["status"] == "new"


def test_blank_incoming_value_never_clears_a_fact_we_hold():
    r = matching.match([_rec(ref="L-1", region=None)], [_live("e1", ref="L-1")], **_KW)[0]
    assert r["status"] == "unchanged"


def test_duplicates_within_one_file():
    res = matching.match([_rec(ref="L-1"), _rec(ref="L-1")], [], **_KW)
    assert [r["status"] for r in res] == ["new", "duplicate"]
    res = matching.match([_rec(ref="A"), _rec(ref="B")], [_live("e1", ref="A"), _live("e2", ref="B")], **_KW)
    assert [r["status"] for r in res] == ["unchanged", "unchanged"]
    res = matching.match([_rec(), _rec(name="depot a")], [_live("e1")], **_KW)   # both claim the same live asset
    assert [r["status"] for r in res] == ["unchanged", "duplicate"]


def test_large_changes_are_flagged():
    r = matching.match([_rec(ref="L-1", value=2_000_000.0)], [_live("e1", ref="L-1")], **_KW)[0]
    assert r["status"] == "update" and r["large"] == ["value changes by +100%"]
    r = matching.match([_rec(ref="L-1", lat=48.87)], [_live("e1", ref="L-1")], **_KW)[0]
    assert r["moved"] and any("location moves" in x for x in r["large"])
    s = matching.summarize([r], ["Depot A"])
    assert s["update"] == 1 and s["large_changes"][0]["name"] == "Depot A"


def _bank_row(**kw):
    row = {"asset_name": "A", "asset_type": "cre", "sector": "RE", "latitude": 48.85, "longitude": 2.35,
           "appraised_value_eur": 1_000_000.004, "counterparty_evic_eur": 5e7}
    row.update(kw)
    return row


def test_build_rejects_rows_the_engine_cannot_use():
    ctx = {"default_entity": None}
    with pytest.raises(RowIssue, match="0,0"):
        BANK.build(ctx, _bank_row(latitude=0, longitude=0))
    with pytest.raises(RowIssue, match="greater than zero"):
        BANK.build(ctx, _bank_row(appraised_value_eur=-5))
    with pytest.raises(RowIssue, match="year_built"):
        INSURANCE.build(ctx, {"policy_name": "P", "latitude": 48.8, "longitude": 2.3, "sum_insured_eur": 10, "year_built": 1066})
    with pytest.raises(RowIssue, match="fraction"):
        INSURANCE.build(ctx, {"policy_name": "P", "latitude": 48.8, "longitude": 2.3, "sum_insured_eur": 10, "deductible_pct": 2})


def test_build_stores_money_at_book_precision():
    assert BANK.build({}, _bank_row())["primary_value_eur"] == 1_000_000.0


def test_insurance_blank_type_and_deductible_are_not_defaulted_at_build():
    rec = INSURANCE.build({}, {"policy_name": "P", "latitude": 48.8, "longitude": 2.3, "sum_insured_eur": 10})
    assert rec["entity_type"] is None and rec["deductible_pct"] is None   # defaults apply only when inserting a new asset


def test_mapping_suggest_and_validate():
    specs = [{"name": "asset_name"}, {"name": "latitude"}, {"name": "longitude"}, {"name": "appraised_value_eur", "kind": "money"},
             {"name": "external_ref"}]
    s = mapping.suggest(["Name", "Lat", "Lng", "Collateral Value", "Loan ID"], specs)
    assert s == {"asset_name": "Name", "latitude": "Lat", "longitude": "Lng", "appraised_value_eur": "Collateral Value",
                 "external_ref": "Loan ID"}
    with pytest.raises(mapping.MappingError, match="two fields"):
        mapping.validate_profile({"asset_name": "X", "external_ref": "X"}, {}, specs)
    with pytest.raises(mapping.MappingError, match="not a money field"):
        mapping.validate_profile({"asset_name": "X"}, {"asset_name": {"multiply": 1000}}, specs)
