"""Pillar 3 Template 5 grid — the physical-risk matrix built to the ITS (EU) 2022/2453 structure.
Verifies the NACE-section bucketing, the chronic/acute classification, and the aggregation invariants."""
from services.governance.pillar3_templates import (
    ACUTE_HAZARDS,
    CHRONIC_HAZARDS,
    HIGH_CLIMATE_NACE,
    _asset_hits,
    _section,
    concentration_split,
    gar_grid,
    template1_grid,
    template5_grid,
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
    # alignment / Paris-benchmark / impairment columns are declared customer-supplied, not fabricated
    assert any("Taxonomy-aligned" in c for c in g["customer_columns"])
    assert any("accumulated impairment" in c for c in g["customer_columns"])
    # no per-loan maturity/IFRS-9 attrs supplied → computed but uncovered, not silently dropped as "customer data"
    assert not g["maturity_covered"] and not g["ifrs9_covered"]
    assert not any("Stage 2" in c for c in g["customer_columns"])   # Stage 2 IS computed now (Fix 3), not declared


def test_template1_wires_maturity_and_ifrs9_from_provided_attrs():
    # Fix 3: Template 1 must compute the same maturity-bucket / IFRS-9 staging columns Template 5 does, from
    # the same per-loan attributes, instead of declaring them customer/IFRS-9 data it "doesn't hold".
    assets = [
        {"nace_code": "D35", "outstanding_loan_balance_eur": 1000, "residual_maturity_years": 3, "ifrs9_stage": "2",
         "ghg1": 0, "ghg2": 0, "ghg3": 0},
        {"nace_code": "D35", "outstanding_loan_balance_eur": 2000, "residual_maturity_years": 12, "ifrs9_stage": "1",
         "ghg1": 0, "ghg2": 0, "ghg3": 0},
    ]
    g = template1_grid(assets)
    assert g["maturity_covered"] and g["ifrs9_covered"]
    by = {r["section"]: r for r in g["rows"]}
    assert by["D"]["le5"] == 1000 and by["D"]["m10_20"] == 2000
    assert by["D"]["avg_maturity"] == 9.0
    assert by["D"]["stage2"] == 1000 and by["D"]["npe"] == 0
    assert by["D"]["has_maturity"] and by["D"]["has_ifrs9"]


def test_no_stated_maturity_routes_to_gt20_not_silently_excluded():
    """EBA Q&A 2022_6515: an exposure with no stated maturity BY ITS NATURE (equity, perpetual instrument)
    must be disclosed in the '>20 years' bucket, never dropped out of the maturity coverage stats — a real
    bug found by a systematic EBA Q&A sweep. A genuinely-missing-data loan (no residual_maturity_years and
    no no_stated_maturity flag) must stay excluded, since that's a different (honest data-gap) case."""
    assets = [
        {"nace_code": "D35", "outstanding_loan_balance_eur": 1000, "residual_maturity_years": 3,
         "ghg1": 0, "ghg2": 0, "ghg3": 0},
        # equity holding: no residual_maturity_years, but flagged no_stated_maturity -> must land in gt20
        {"nace_code": "D35", "outstanding_loan_balance_eur": 500, "no_stated_maturity": True,
         "ghg1": 0, "ghg2": 0, "ghg3": 0},
        # genuinely missing data: neither field supplied -> stays excluded (not gt20, not counted at all)
        {"nace_code": "D35", "outstanding_loan_balance_eur": 300, "ghg1": 0, "ghg2": 0, "ghg3": 0},
    ]
    g = template1_grid(assets)
    by = {r["section"]: r for r in g["rows"]}
    assert g["maturity_covered"]
    assert by["D"]["le5"] == 1000
    assert by["D"]["gt20"] == 500          # the no_stated_maturity exposure, correctly bucketed
    # the weighted-average maturity is computed only over exposures with a REAL numeric maturity (the
    # no_stated_maturity row has no number to average in, so avg stays anchored to the €1000 le5 exposure)
    assert by["D"]["avg_maturity"] == 3.0
    # the genuinely-missing-data €300 loan contributes to neither le5 nor gt20 — still an honest gap
    assert by["D"]["le5"] + by["D"]["m5_10"] + by["D"]["m10_20"] + by["D"]["gt20"] == 1500


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


def test_template5_maturity_and_ifrs9_from_provided_attrs():
    # maturity buckets + gross-weighted average + IFRS-9 staging come from the provided per-loan attributes;
    # a sector/loan without them must stay blank (not €0), so coverage is tracked per row.
    assets = [
        {"nace_code": "D35", "outstanding_loan_balance_eur": 1000, "residual_maturity_years": 3, "ifrs9_stage": "2", "hazards": []},
        {"nace_code": "D35", "outstanding_loan_balance_eur": 2000, "residual_maturity_years": 12, "ifrs9_stage": "1", "hazards": []},
        {"nace_code": "A01", "outstanding_loan_balance_eur": 500, "residual_maturity_years": 25, "ifrs9_stage": "3", "hazards": []},
        {"nace_code": "A01", "outstanding_loan_balance_eur": 800, "hazards": []},  # no maturity / no stage
    ]
    g = template5_grid(assets)
    assert g["maturity_covered"] and g["ifrs9_covered"]
    by = {r["section"]: r for r in g["rows"]}
    # D: 1000@3y -> ≤5y ; 2000@12y -> 10–20y ; gross-weighted avg = (1000*3+2000*12)/3000 = 9.0
    assert by["D"]["le5"] == 1000 and by["D"]["m10_20"] == 2000 and by["D"]["avg_maturity"] == 9.0
    assert by["D"]["stage2"] == 1000 and by["D"]["npe"] == 0
    # A: only the 500@25y loan carries attributes -> >20y bucket; Stage 3 -> non-performing; the 800 loan is excluded
    assert by["A"]["gt20"] == 500 and by["A"]["npe"] == 500 and by["A"]["avg_maturity"] == 25.0
    assert by["A"]["has_maturity"] and by["A"]["has_ifrs9"]
    # total weighted average across all loans that carry maturity
    assert g["total"]["avg_maturity"] == round((500 * 25 + 1000 * 3 + 2000 * 12) / 3500, 1)
    # impairment is still declared customer-supplied (never fabricated)
    assert any("impairment" in c for c in g["customer_columns"])


def test_template5_geography_axis_top_n_and_other_rollup():
    # EBA Q&A 2022_6600: Template 5 needs a SEPARATE grid per geography, not one portfolio-wide grid.
    assets = (
        [{"nace_code": "C", "outstanding_loan_balance_eur": 100, "country": "DE", "hazards": []}] +
        [{"nace_code": "A", "outstanding_loan_balance_eur": 50, "country": "FR", "hazards": []}] +
        [{"nace_code": "C", "outstanding_loan_balance_eur": 5, "country": f"C{i}", "hazards": []} for i in range(12)]
    )
    g = template5_grid(assets)
    # portfolio-wide top level is unchanged (existing consumers keep working)
    assert g["total"]["gross"] == 100 + 50 + 12 * 5
    geos = {x["country"]: x for x in g["geographies"]}
    # top 10 by exposure = DE(100), FR(50), then 8 of the 12 C0..C11 at 5 each; the remaining 4 roll into OTHER
    assert len(g["geographies"]) == 11   # 10 named + 1 "Other / rest of book"
    assert "DE" in geos and "FR" in geos and "OTHER" in geos
    assert geos["DE"]["exposure_eur"] == 100
    assert geos["DE"]["rows"][0]["section"] == "C" and geos["DE"]["rows"][0]["gross"] == 100
    other = geos["OTHER"]
    assert other["label"] == "Other / rest of book"
    assert other["exposure_eur"] == 4 * 5    # the 4 smallest countries that didn't make the top 10
    # nothing silently disappears: sum of every geography's gross == the portfolio total
    assert sum(x["total"]["gross"] for x in g["geographies"]) == g["total"]["gross"]
    assert "geography" in g["basis"].lower()


def test_template5_geography_no_rollup_when_within_top_n():
    assets = [{"nace_code": "C", "outstanding_loan_balance_eur": 10, "country": "DE", "hazards": []},
              {"nace_code": "A", "outstanding_loan_balance_eur": 5, "country": "FR", "hazards": []}]
    g = template5_grid(assets)
    assert len(g["geographies"]) == 2
    assert {x["country"] for x in g["geographies"]} == {"DE", "FR"}


def test_template5_columns_blank_when_no_attrs_provided():
    assets = [{"nace_code": "C", "outstanding_loan_balance_eur": 1000, "hazards": []}]
    g = template5_grid(assets)
    assert not g["maturity_covered"] and not g["ifrs9_covered"]
    assert g["rows"][0]["has_maturity"] is False and g["rows"][0]["avg_maturity"] is None


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
