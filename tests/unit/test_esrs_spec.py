"""The ESRS specification family (E1, E3, E4) and its binding: every version valid, every printed datapoint bound to a
concept, the version that governs each financial year (with the Art. 2 election of 2026/1563 and a non-calendar year),
and the undertaking never asked to provide what the platform computes."""
from __future__ import annotations

import pytest

import services.regspec as R
from services.governance import esrs_binding as B
from services.regspec.bindings import binding_for

VERSIONS = ("dr_2023_2772", "dr_2023_2772_as_2025_1416", "dr_2026_1563")


@pytest.mark.parametrize("v", VERSIONS)
def test_each_version_is_valid_and_fully_bound(v):
    spec = R.load("esrs", v)
    assert R.validate(spec) == []
    assert R.coverage(spec, binding_for("esrs", spec))["complete"]
    cov = B.coverage(spec)
    assert cov["complete"], (cov["missing"], cov["stale"], cov["invalid"])
    assert {t["id"] for t in spec["templates"]} == {"E1", "E3", "E4"}
    assert all(i.get("datapoints") for t in spec["templates"] for i in t["items"] if i["kind"] == "field")


@pytest.mark.parametrize("period_end, elections, version", [
    ("2024-12-31", None, "dr_2023_2772"),
    ("2025-12-31", None, "dr_2023_2772_as_2025_1416"),
    ("2026-12-31", None, "dr_2023_2772_as_2025_1416"),
    ("2026-12-31", {"esrs_fy2026_version": "dr_2026_1563"}, "dr_2026_1563"),
    ("2026-12-31", {"esrs_fy2026_version": "dr_2023_2772_as_2025_1416_with_2026_1563_reliefs"}, "dr_2023_2772_as_2025_1416"),
    ("2027-06-30", None, "dr_2023_2772_as_2025_1416"),        # the year began on 1 July 2026
    ("2027-12-31", None, "dr_2026_1563"),
    ("2027-12-31", {"esrs_fy2026_version": "dr_2023_2772_as_2025_1416"}, "dr_2026_1563"),   # an FY2026 election only
])
def test_the_version_governing_a_financial_year(period_end, elections, version):
    assert R.governing("esrs", period_end=period_end, elections=elections)["version"] == version


def test_the_undertaking_provides_only_what_the_platform_does_not_compute():
    for v in VERSIONS:
        spec = R.load("esrs", v)
        cat = B.provided_catalog(spec)
        assert cat and all(B.concepts()[k]["lane"] == "provided" for k in cat)
        assert not {"e1.physrisk.assets.amount", "e4.sites.sensitive.count"} & set(cat)
    # a concept keeps its key across versions: Scope 1 is E1-6 §48(a) in 2023 and E1-8 §30(a)(i) in 2026
    old, new = B.binding("dr_2023_2772_as_2025_1416"), B.binding("dr_2026_1563")
    assert old["E1-6.48a:scope1_gross"] == new["E1-8.30a.i:scope1_ghg"] == "e1.ghg.scope1.gross"
