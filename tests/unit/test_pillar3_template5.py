"""Pillar 3 shared pieces: the chronic/acute hazard split, the GAR grid and the concentration measures.
Templates 1 and 5 are tested against their specification in test_pillar3_grids.py."""
from services.governance.pillar3_templates import (
    ACUTE_HAZARDS,
    CHRONIC_HAZARDS,
    HIGH_CLIMATE_NACE,
    _asset_hits,
    _section,
    concentration_split,
)

LEVEL = 50.0      # the institution's stated at-risk level — a test value (method.at_risk_level)


def test_concentration_split_acute_chronic_and_sector():
    assets = [
        _asset("35.11", 200, [("storm", 80)]),                   # electricity (D), acute only
        _asset("01.11", 100, [("drought", 60)]),                 # agriculture (A), chronic only
        _asset("C", 300, [("flood", 85), ("drought", 55)]),      # manufacturing (C), BOTH
        _asset("64.19", 400, [("flood", 40)]),                   # financial (K), below the level → neither
    ]
    c = concentration_split(assets, LEVEL)
    # acute = storm(200) + flood-both(300) = 500 ; chronic = drought(100) + both(300) = 400 (they overlap on the 300)
    assert c["acute_val"] == 500 and c["chronic_val"] == 400
    # high-climate-impact NACE (A–H, L): D+A+C = 600 ; financial K(400) is NOT in the high-impact set
    assert c["high_climate_val"] == 600
    assert "K" not in HIGH_CLIMATE_NACE
    # most-concentrated single sector = financial K at 400
    assert c["top_sector"] == "K" and c["top_sector_val"] == 400
    # acute/chronic are overlapping lenses, not a partition — each ≤ total book
    assert c["acute_val"] <= 1000 and c["chronic_val"] <= 1000
    # without a stated level the split is a gap, the sector concentration (no level needed) is not
    g = concentration_split(assets, None)
    assert g["acute_val"] is None and g["chronic_val"] is None and g["high_climate_val"] == 600


def _asset(nace, value, hazards):
    return {"nace_code": nace, "value_eur": value, "outstanding_loan_balance_eur": value,
            "hazards": [{"hazard": h, "score": sc} for h, sc in hazards]}


def test_nace_section_mapping():
    assert _section("C") == "C"           # section letter
    assert _section("01.11") == "A"       # crop division → Agriculture
    assert _section("35.11") == "D"       # electricity → D
    assert _section("41.20") == "F"       # construction → F
    assert _section(None) == "?"          # missing → unclassified


def test_chronic_acute_classification_at_the_stated_level():
    # an acute peril at the level + a chronic one below it → acute only
    chronic, acute = _asset_hits(_asset("C", 1, [("flood", 50), ("drought", 49.9)]), LEVEL)
    assert acute and not chronic
    # both at or above → both
    chronic, acute = _asset_hits(_asset("C", 1, [("drought", 70), ("storm", 60)]), LEVEL)
    assert chronic and acute
    # both below → neither; the same asset at a lower stated level → both
    low = _asset("C", 1, [("flood", 30), ("drought", 20)])
    assert _asset_hits(low, LEVEL) == (False, False) and _asset_hits(low, 20.0) == (True, True)
    # a scale that does not apply to the exposure never makes it sensitive
    assert _asset_hits({"hazards": [{"hazard": "flood", "score": 90, "relevant": False}]}, LEVEL) == (False, False)


def test_hazard_sets_are_disjoint_and_climate_only():
    assert ACUTE_HAZARDS.isdisjoint(CHRONIC_HAZARDS)
    # non-climate perils are excluded from Template 5 (climate physical risk only)
    for peril in ("seismic", "volcanic", "pollution"):
        assert peril not in ACUTE_HAZARDS and peril not in CHRONIC_HAZARDS
