"""Pillar 3 Template 5 grid — the physical-risk matrix built to the ITS (EU) 2022/2453 structure.
Verifies the NACE-section bucketing, the chronic/acute classification, and the aggregation invariants."""
from services.governance.pillar3_templates import (
    template5_grid, template1_grid, gar_grid, concentration_split, _section, _asset_hits,
    ACUTE_HAZARDS, CHRONIC_HAZARDS, HIGH_CLIMATE_NACE,
)


def test_concentration_split_acute_chronic_and_sector():
    assets = [
        _asset("35.11", 200, [("storm", "VH")]),                 # electricity (D), acute only
        _asset("01.11", 100, [("drought", "H")]),                # agriculture (A), chronic only
        _asset("C", 300, [("flood", "VH"), ("drought", "H")]),   # manufacturing (C), BOTH
        _asset("64.19", 400, [("flood", "M")]),                  # financial (K), not High+ → neither
    ]
    c = concentration_split(assets)
    # acute = storm(200) + flood-both(300) = 500 ; chronic = drought(100) + both(300) = 400 (they overlap on the 300)
    assert c["acute_val"] == 500 and c["chronic_val"] == 400
    # high-climate-impact NACE (A–H, L): D+A+C = 600 ; financial K(400) is NOT in the high-impact set
    assert c["high_climate_val"] == 600
    assert "K" not in HIGH_CLIMATE_NACE
    # most-concentrated single sector = financial K at 400
    assert c["top_sector"] == "K" and c["top_sector_val"] == 400
    # acute/chronic are overlapping lenses, not a partition — each ≤ total book
    assert c["acute_val"] <= 1000 and c["chronic_val"] <= 1000


def test_gar_grid_excludes_government_and_computes_ratio():
    assets = [
        {"nace_code": "64.19", "value_eur": 100, "taxonomy_status": "aligned"},   # financial (K), aligned
        {"nace_code": "35.11", "value_eur": 200, "taxonomy_status": "eligible"},  # non-financial, eligible only
        {"nace_code": "C", "value_eur": 100, "taxonomy_status": "not_eligible"},  # non-financial, not eligible
        {"nace_code": "84.11", "value_eur": 500, "taxonomy_status": "aligned"},   # general government (O) — excluded
    ]
    g = gar_grid(assets)
    assert g["total_assets"] == 900
    assert g["general_government"] == 500
    assert g["covered_assets"] == 400                     # 900 - 500 govt
    assert g["eligible"] == 300                           # 100 aligned + 200 eligible (govt's 500 excluded)
    assert g["aligned"] == 100                            # only the financial one (govt aligned excluded)
    assert g["gar_stock_pct"] == 25.0                     # 100 / 400
    assert g["pct_eligible"] == 75.0                      # 300 / 400
    by = {r["counterparty"]: r for r in g["rows"]}
    assert by["Financial corporations"]["aligned"] == 100
    assert by["General governments"]["gross"] == 500
    # aligned is a subset of eligible on every row
    for r in g["rows"]:
        assert r["aligned"] <= r["eligible"] <= r["gross"]
    # per-objective CCM/CCA split is declared customer, not fabricated
    assert any("CCM" in c for c in g["customer_columns"])


def _asset(nace, gross, hazards):
    return {"nace_code": nace, "outstanding_loan_balance_eur": gross,
            "hazards": [{"hazard": h, "bucket": b} for h, b in hazards]}


def test_template1_transition_grid_emissions_by_sector():
    assets = [
        {"nace_code": "35.11", "outstanding_loan_balance_eur": 200, "ghg1": 100, "ghg2": 50, "ghg3": 300},
        {"nace_code": "C", "outstanding_loan_balance_eur": 100, "ghg1": 10, "ghg2": 5, "ghg3": 20},
    ]
    g = template1_grid(assets)
    by = {r["section"]: r for r in g["rows"]}
    # electricity: gross 200, financed = 100+50+300 = 450, of which Scope 3 = 300
    assert by["D"]["gross"] == 200 and by["D"]["fin_emissions"] == 450 and by["D"]["scope3"] == 300
    # total financed emissions = sum of all scopes (platform's financed-emissions basis); Scope3 subset
    assert g["total"]["fin_emissions"] == 485 and g["total"]["scope3"] == 320
    assert g["total"]["scope3"] <= g["total"]["fin_emissions"]
    # alignment / credit-quality / maturity columns are declared customer-supplied, not fabricated
    assert any("Taxonomy-aligned" in c for c in g["customer_columns"])
    assert any("Stage 2" in c for c in g["customer_columns"])


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
