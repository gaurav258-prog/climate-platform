"""Pillar 3 Template 5 grid — the physical-risk matrix built to the ITS (EU) 2022/2453 structure.
Verifies the NACE-section bucketing, the chronic/acute classification, and the aggregation invariants."""
from services.governance.pillar3_templates import (
    template5_grid, _section, _asset_hits, ACUTE_HAZARDS, CHRONIC_HAZARDS,
)


def _asset(nace, gross, hazards):
    return {"nace_code": nace, "outstanding_loan_balance_eur": gross,
            "hazards": [{"hazard": h, "bucket": b} for h, b in hazards]}


def test_nace_section_mapping():
    assert _section("C") == "C"           # section letter
    assert _section("01.11") == "A"       # crop division → Agriculture
    assert _section("35.11") == "D"       # electricity → D
    assert _section("41.20") == "F"       # construction → F
    assert _section(None) == "?"          # missing → unclassified


def test_chronic_acute_classification_high_plus_only():
    # a High+ acute peril + a Medium chronic peril → acute only (M doesn't count)
    chronic, acute = _asset_hits(_asset("C", 1, [("flood", "VH"), ("drought", "M")]))
    assert acute and not chronic
    # High+ chronic + High+ acute → both
    chronic, acute = _asset_hits(_asset("C", 1, [("drought", "H"), ("storm", "H")]))
    assert chronic and acute
    # only Low/Medium → neither
    assert _asset_hits(_asset("C", 1, [("flood", "M"), ("drought", "L")])) == (False, False)


def test_hazard_sets_are_disjoint_and_climate_only():
    assert ACUTE_HAZARDS.isdisjoint(CHRONIC_HAZARDS)
    # non-climate perils are excluded from Template 5 (climate physical risk only)
    for peril in ("seismic", "volcanic", "pollution"):
        assert peril not in ACUTE_HAZARDS and peril not in CHRONIC_HAZARDS


def test_grid_aggregation_and_invariants():
    assets = [
        _asset("C", 100, [("flood", "VH")]),                    # manufacturing, acute
        _asset("35.11", 200, [("drought", "H"), ("storm", "H")]),  # electricity, both
        _asset("01.11", 50, [("heat_chronic", "VH")]),          # agriculture, chronic
        _asset("C", 40, [("flood", "M")]),                      # manufacturing, not sensitive
    ]
    g = template5_grid(assets)
    sectors = {r["section"]: r for r in g["rows"]}
    # manufacturing: gross 140, sensitive 100 (the M one doesn't count), acute 100, chronic 0, both 0
    assert sectors["C"]["gross"] == 140 and sectors["C"]["sensitive"] == 100
    assert sectors["C"]["acute"] == 100 and sectors["C"]["chronic"] == 0 and sectors["C"]["both"] == 0
    # electricity: both chronic+acute
    assert sectors["D"]["both"] == 200 and sectors["D"]["chronic"] == 200 and sectors["D"]["acute"] == 200
    # invariants across every row + total: both ≤ chronic,acute ≤ sensitive ≤ gross
    for r in g["rows"] + [g["total"]]:
        assert r["both"] <= r["chronic"] <= r["sensitive"] <= r["gross"]
        assert r["both"] <= r["acute"] <= r["sensitive"] <= r["gross"]
    assert g["total"]["gross"] == 390 and g["total"]["sensitive"] == 350
    # the columns we can't source are declared, not silently dropped
    assert any("maturity" in c for c in g["customer_columns"])
    assert any("Stage 2" in c for c in g["customer_columns"])
