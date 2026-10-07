"""The demo building facts (scripts/seed_demo_building_facts.py): stated only where the asset type does not settle the
use, the same answer every run, and a building value inside its declared share of the stated value."""
from scripts.seed_demo_building_facts import BUILDING_SHARE, building_value_for, use_for


def test_a_use_the_type_settles_is_left_to_the_crosswalk():
    assert use_for({"entity_id": "a", "vertical": "banking", "entity_type": "office"}) is None
    assert use_for({"entity_id": "a", "vertical": "banking", "entity_type": "hospitality"}) == "commercial"
    assert use_for({"entity_id": "a", "vertical": "realestate", "entity_type": "logistics"}) == "industrial"


def test_an_insured_property_gets_the_same_use_every_run():
    r = {"entity_id": "11111111-2222-4333-8444-555555555555", "vertical": "insurance", "entity_type": "property"}
    assert use_for(r) == use_for(r) in ("residential", "commercial", "industrial")


def test_a_building_value_lies_inside_its_declared_share_and_insurers_keep_theirs():
    lo, hi = BUILDING_SHARE
    for i in range(50):
        v = building_value_for({"entity_id": f"e{i}", "vertical": "realestate", "value": 1_000_000.0})
        assert lo * 1_000_000 <= v <= hi * 1_000_000
    assert building_value_for({"entity_id": "e", "vertical": "insurance", "value": 1_000_000.0}) is None
