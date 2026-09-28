"""Pillar 3 shared pieces: the chronic/acute hazard split, the GAR grid and the concentration measures.
Templates 1 and 5 are tested against their specification in test_pillar3_grids.py."""
from services.governance.pillar3_templates import (
    ACUTE_HAZARDS,
    CHRONIC_HAZARDS,
    HIGH_CLIMATE_NACE,
    _asset_hits,
    _section,
    concentration_split,
    gar_grid,
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


def test_gar_grid_excludes_only_central_government():
    assets = [
        {"nace_code": "64.19", "value_eur": 100, "taxonomy_status": "aligned"},   # financial (K), aligned
        {"nace_code": "35.11", "value_eur": 200, "taxonomy_status": "eligible"},  # non-financial, eligible only
        {"nace_code": "C", "value_eur": 100, "taxonomy_status": "not_eligible"},  # non-financial, not eligible
        {"nace_code": "84.11", "value_eur": 500, "taxonomy_status": "aligned",
         "counterparty_govt_level": "central"},                                  # central govt (O) — excluded
        {"nace_code": "84.12", "value_eur": 300, "taxonomy_status": "aligned",
         "counterparty_govt_level": "local"},                                    # local govt (O) — NOT excluded
    ]
    g = gar_grid(assets)
    assert g["total_assets"] == 1200
    assert g["general_government"] == 500                 # only the central-govt exposure
    assert g["covered_assets"] == 700                      # 1200 - 500 central govt
    assert g["eligible"] == 600                            # 100 + 200 + 300 (govt's 500 excluded)
    assert g["aligned"] == 400                             # 100 financial + 300 local govt (central govt's 500 excluded)
    assert g["gar_stock_pct"] == round(400 / 700 * 100, 1)
    assert g["pct_eligible"] == round(600 / 700 * 100, 1)
    by = {r["counterparty"]: r for r in g["rows"]}
    assert by["Financial corporations"]["aligned"] == 100
    assert by["General governments"]["gross"] == 500       # central govt only
    assert by["Non-financial corporations"]["gross"] == 200 + 100 + 300   # includes the local-govt exposure
    # aligned is a subset of eligible on every row
    for r in g["rows"]:
        assert r["aligned"] <= r["eligible"] <= r["gross"]
    # per-objective CCM/CCA split is declared customer, not fabricated
    assert any("CCM" in c for c in g["customer_columns"])
    assert g["govt_level_coverage"] == {"n_nace_o": 2, "n_signalled": 2}


def test_gar_grid_unsignalled_nace_o_defaults_to_in_scope_not_excluded():
    # a NACE-O counterparty with NO counterparty_govt_level must NOT be excluded — the bug this fixes was
    # excluding it by default; the conservative fix keeps it in scope (covered assets) until signalled.
    assets = [
        {"nace_code": "84.11", "value_eur": 400, "taxonomy_status": "eligible"},   # no govt_level at all
    ]
    g = gar_grid(assets)
    assert g["general_government"] == 0
    assert g["covered_assets"] == 400
    by = {r["counterparty"]: r for r in g["rows"]}
    assert "General governments" not in by
    assert by["Non-financial corporations"]["gross"] == 400
    assert g["govt_level_coverage"] == {"n_nace_o": 1, "n_signalled": 0}
    assert "counterparty_govt_level" in g["basis"] and "IN SCOPE" in g["basis"]


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
