"""The holdings look-through's rules (the product owner's decisions of 2026-10-22), without a database.

  weights     a weight on the assets basis always counts as a share of value; revenue, production capacity and headcount
              only when the organisation states it (one governed switch each, no default); 'equal' is never offered
  sites       a head office found from the company's address is a proxy, not a physical site; a site's use is read only
              where its type is unambiguous (a warehouse is not)"""
from __future__ import annotations

from services.calc_settings import INTERPRETATION_SCHEMA, interpretation_catalog
from services.loss import lookthrough, registry
from services.reference.footprint import PROXY, is_hq_proxy


def test_assets_always_count_and_other_bases_only_when_stated():
    assert lookthrough.accepted_bases({}) == ["assets"]
    stated = {lookthrough.switch("revenue"): lookthrough.COUNTS, lookthrough.switch("headcount"): "not_counted"}
    assert lookthrough.accepted_bases(stated) == ["assets", "revenue"]
    assert "equal" not in lookthrough.STATED_BASES and "assets" not in lookthrough.STATED_BASES


def test_each_stated_basis_is_a_governed_switch_with_no_default():
    for b in lookthrough.STATED_BASES:
        spec = INTERPRETATION_SCHEMA[lookthrough.switch(b)]
        assert spec["default"] is None and spec["kind"] == "enum" and lookthrough.COUNTS in spec["allowed"]
    offered = {s["key"]: s for s in interpretation_catalog("asset_manager")}
    for b in lookthrough.STATED_BASES:
        s = offered[lookthrough.switch(b)]
        assert {o["label"] for o in s["options"]} == {"Counts as a share of value", "Does not count"}
    assert lookthrough.switch("revenue") not in {s["key"] for s in interpretation_catalog("bank")}


def test_the_head_office_proxy_and_the_site_uses():
    assert is_hq_proxy(PROXY["source"], PROXY["facility_type"]) and not is_hq_proxy("manual", "hq")
    uses = [registry.occupancy_of(None, "issuer_facilities.facility_type", t)[0] for t in ("plant", "office", "hq", "warehouse")]
    assert uses == ["industrial", "commercial", "commercial", None]
