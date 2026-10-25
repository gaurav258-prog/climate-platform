"""PCAF mortgages (Part A, 3rd ed., §5.5; data/reference/pcaf/part_a_2025.json): the attribution, the building's emissions
by every data quality option of Table 5.5-1, every named gap, and the book as Table 10.2-2 reports an asset class — each
figure checked by hand-computable arithmetic."""
from __future__ import annotations

import importlib
import re

import pytest

from services.ingest.fields import VOCABS
from services.scoring import pcaf_mortgages as pm
from services.scoring.pcaf import asset_financed, book_financed_emissions


def _row(source, basis, *, kwh=None, per_m2=None, buildings=None, ef=0.2, ef_type="average", year=2025):
    return {"energy_source": source, "energy_basis": basis, "annual_kwh": kwh, "kwh_per_m2": per_m2, "buildings": buildings,
            "emission_factor_kg_per_kwh": ef, "emission_factor_type": ef_type if ef is not None else None,
            "energy_year": year}


def _mortgage(out=300_000, v0=400_000, vf=None, floor=None, rows=(), epc=None):
    return {"pcaf_asset_class": "mortgages", "outstanding_loan_balance_eur": out, "property_value_at_origination_eur": v0,
            "property_value_fixed_eur": vf, "floor_area_m2": floor, "building_energy": list(rows), "epc_label": epc}


# ── attribution (§5.5 p. 84) ──

def test_attribution_is_the_outstanding_amount_over_the_value_at_origination():
    assert pm.attribution(_mortgage()) == (0.75, "at_origination", None)


def test_where_the_value_at_origination_is_not_stated_the_fixed_latest_value_is_the_denominator():
    assert pm.attribution(_mortgage(v0=None, vf=500_000)) == (0.6, "latest_fixed", None)


def test_the_value_at_origination_comes_first_when_both_are_stated():
    """The latest value stands in only where the value at origination cannot be obtained: stated, it is used."""
    assert pm.attribution(_mortgage(v0=400_000, vf=500_000))[1] == "at_origination"


def test_without_a_property_value_or_an_outstanding_amount_the_attribution_is_a_named_gap():
    assert pm.attribution(_mortgage(v0=None)) == (None, None, "no_property_value")
    assert pm.attribution(_mortgage(out=None)) == (None, None, "no_outstanding")


def test_an_outstanding_amount_above_the_property_value_is_computed_as_written_and_counted():
    """§5.5 states no cap (the open reading recorded in the reference file): the factor is the formula's, and the book
    counts the loans above 1."""
    m = _mortgage(out=500_000, v0=400_000, rows=[_row("electricity", "metered", kwh=1000)])
    assert pm.loan(m)["attribution_factor"] == 1.25
    assert pm.book([m])["n_attribution_above_one"] == 1
    assert pm.reference()["mortgages"]["attribution"]["cap"] is None


# ── the building's emissions by every option of Table 5.5-1 ──

@pytest.mark.parametrize("rows, floor, s1, s2, option, score", [
    # 1a: metered, the supplier's factors — gas 10,000 kWh × 0.2 kg = 2 t (scope 1), electricity 3,000 × 0.4 = 1.2 t (2)
    ([_row("natural_gas", "metered", kwh=10_000, ef_type="supplier_specific"),
      _row("electricity", "metered", kwh=3_000, ef=0.4, ef_type="supplier_specific")], None, 2.0, 1.2, "1a", 1),
    # 1b: metered, average factors
    ([_row("heating_oil", "metered", kwh=10_000, ef=0.3)], None, 3.0, 0.0, "1b", 2),
    # 2a: 120 kWh/m² from the energy label × 95 m² × 0.2 kg = 2.28 t
    ([_row("natural_gas", "energy_label", per_m2=120)], 95, 2.28, 0.0, "2a", 3),
    # 2b: statistics per m² — district heating is bought heat: scope 2
    ([_row("district_heating", "statistics_per_m2", per_m2=100, ef=0.15)], 80, 0.0, 1.2, "2b", 4),
    # 3: statistics per building — 12,000 kWh × 2 buildings × 0.2 kg = 4.8 t
    ([_row("lpg", "statistics_per_building", kwh=12_000, buildings=2)], None, 4.8, 0.0, "3", 5),
])
def test_each_data_quality_option_gives_its_score_and_the_scoped_emissions(rows, floor, s1, s2, option, score):
    r = pm.loan(_mortgage(floor=floor, rows=rows))
    assert r["gaps"] == []
    assert (r["building_scope1_tco2e"], r["building_scope2_tco2e"]) == (pytest.approx(s1), pytest.approx(s2))
    assert (r["dq_option"], r["dq_score"], r["dq_gap"]) == (option, score, None)
    assert r["financed_tco2e"] == pytest.approx(0.75 * (s1 + s2))


def test_a_building_read_by_two_options_has_its_emissions_but_no_score_in_the_table():
    r = pm.loan(_mortgage(floor=90, rows=[_row("electricity", "metered", kwh=2_000, ef=0.4),
                                          _row("natural_gas", "energy_label", per_m2=100)]))
    assert r["financed_tco2e"] == pytest.approx(0.75 * (0.8 + 1.8))
    assert (r["dq_score"], r["dq_gap"]) == (None, "mixed")


def test_an_estimate_with_the_suppliers_own_factor_is_no_option_of_the_table():
    r = pm.loan(_mortgage(floor=90, rows=[_row("natural_gas", "energy_label", per_m2=100, ef_type="supplier_specific")]))
    assert r["financed_tco2e"] == pytest.approx(0.75 * 1.8)
    assert (r["dq_score"], r["dq_gap"]) == (None, "no_option")


def test_the_building_reads_its_most_recent_year_only():
    """§6.1: the most recent data. Oil burnt in 2024 is not summed into 2025, whose rows state a heat pump's electricity."""
    r = pm.loan(_mortgage(rows=[_row("heating_oil", "metered", kwh=15_000, ef=0.3, year=2024),
                                _row("electricity", "metered", kwh=4_000, ef=0.4, year=2025)]))
    assert (r["building_scope1_tco2e"], r["building_scope2_tco2e"]) == (0.0, 1.6)


# ── named gaps, in the order the formula needs them ──

@pytest.mark.parametrize("m, gaps", [
    (_mortgage(), ["no_energy"]),
    (_mortgage(epc="C"), ["label_without_energy"]),       # a label class is a range, not an energy figure
    (_mortgage(rows=[_row("natural_gas", "energy_label", per_m2=120)]), ["no_floor_area"]),
    (_mortgage(rows=[_row("natural_gas", "metered", kwh=9_000, ef=None)]), ["no_emission_factor"]),
    (_mortgage(v0=None, floor=None, rows=[_row("natural_gas", "energy_label", per_m2=120, ef=None),
                                          _row("electricity", "statistics_per_m2", per_m2=30)]),
     ["no_property_value", "no_floor_area", "no_emission_factor"]),
    (_mortgage(out=None, v0=None), ["no_outstanding", "no_energy"]),
])
def test_every_missing_input_is_a_named_gap_never_a_number(m, gaps):
    r = pm.loan(m)
    assert r["gaps"] == gaps
    assert "financed_tco2e" not in r


# ── the book (Table 10.2-2; the weighted score, §6.1 pp. 167-168) ──

def test_the_book_sums_the_mortgages_with_a_figure_and_weights_the_score_by_outstanding_amount():
    a = _mortgage(out=300_000, floor=100, rows=[_row("natural_gas", "energy_label", per_m2=100)])          # 2 t × 0.75, score 3
    b = _mortgage(out=100_000, v0=200_000, rows=[_row("electricity", "metered", kwh=5_000, ef=0.4,
                                                     ef_type="supplier_specific")])                       # 2 t × 0.5, score 1
    c = _mortgage(out=50_000, epc="D")                                                                     # gap
    d = _mortgage(out=50_000, v0=None, rows=[_row("electricity", "metered", kwh=1_000)])                   # gap
    bk = pm.book([a, b, c, d, {"pcaf_asset_class": None, "outstanding_loan_balance_eur": 9e6}])
    assert (bk["n_loans"], bk["n_with_emissions"], bk["outstanding_eur"], bk["covered_outstanding_eur"]) == \
        (4, 2, 500_000, 400_000)
    assert (bk["scope1"], bk["scope2"], bk["scope12"]) == (2, 1, 2)    # 1.5 t and 1.0 t: whole tonnes each, the sum of 2.5
    assert bk["coverage_pct"] == 80.0
    assert bk["dq_score"] == 2.5                                        # (300k × 3 + 100k × 1) / 400k
    assert bk["by_score"] == {"1": {"n": 1, "outstanding_eur": 100_000, "financed_tco2e": 1.0},
                              "3": {"n": 1, "outstanding_eur": 300_000, "financed_tco2e": 1.5}}
    assert bk["gaps"] == [{"reason": "no_property_value", "n": 1, "outstanding_eur": 50_000},
                          {"reason": "label_without_energy", "n": 1, "outstanding_eur": 50_000}]
    assert a["pcaf_mortgage"]["dq_score"] == 3                          # each asset carries its own figure for the drills


def test_a_book_without_a_mortgage_figure_has_no_total_and_no_score():
    bk = pm.book([_mortgage(epc="B")])
    assert (bk["scope12"], bk["dq_score"], bk["coverage_pct"]) == (None, None, 0.0)


def test_the_loan_book_attributes_each_class_by_its_own_method_and_combines_them():
    company = {"pcaf_asset_class": None, "outstanding_loan_balance_eur": 1e6, "evic_eur": 1e8,
               "ghg1": 10_000, "ghg2": 5_000, "ghg3": 85_000}                                               # 1 % → 1,000 t
    mortgage = _mortgage(rows=[_row("natural_gas", "metered", kwh=20_000)])                                # 0.75 × 4 t = 3 t
    cre = {"pcaf_asset_class": "commercial_real_estate", "outstanding_loan_balance_eur": 2e6, "evic_eur": 1e7,
           "ghg1": 1, "ghg2": 1, "ghg3": 1}
    home = {"pcaf_asset_class": None, "counterparty_sector": "household", "outstanding_loan_balance_eur": 250_000}
    out = book_financed_emissions([company, mortgage, cre, home], exposure_key="outstanding_loan_balance_eur",
                                  evic_key="evic_eur")
    assert out["combined"] == {"scope1": 103, "scope2": 50, "scope3": 850, "total": 1003}
    assert out["mortgages"]["scope12"] == 3 and out["n_evic_covered"] == 1
    # a commercial real-estate loan is never attributed by an EVIC: its method (§5.4) is not built
    assert out["not_built"] == [{"asset_class": "commercial_real_estate", "n": 1, "outstanding_eur": 2_000_000}]
    assert out["class_not_stated"] == {"n": 1, "outstanding_eur": 250_000}
    # each loan's part, by the same rules, adds up to the total
    assert sum(asset_financed(a)["total"] or 0 for a in (company, mortgage, cre, home)) == pytest.approx(1003)


def test_a_company_stating_one_scope_is_in_that_scope_and_not_in_the_total():
    """E79 for the drills (E339): each loan's part of the total counts it only where the total does."""
    one = {"outstanding_loan_balance_eur": 1e6, "evic_eur": 1e7, "ghg1": 100, "ghg2": None, "ghg3": None}
    assert asset_financed(one) == {"scope1": 10.0, "scope2": None, "scope3": None, "total": None}


# ── the reference file and what reads it ──

def test_table_5_5_1_scores_are_one_to_five_once_each_and_every_basis_has_an_option():
    opts = pm.reference()["mortgages"]["data_quality"]["options"]
    assert sorted(o["score"] for o in opts) == [1, 2, 3, 4, 5]
    assert {o["energy_basis"] for o in opts} == set(pm.reference()["mortgages"]["energy_bases"])


def test_the_vocabularies_are_the_reference_files_lists():
    ref = pm.reference()
    assert VOCABS["pcaf_asset_class"].values == tuple(c["key"] for c in ref["asset_classes"])
    assert set(VOCABS["energy_basis"].values) == set(ref["mortgages"]["energy_bases"])
    scoped, refused = ref["mortgages"]["energy_sources"]["scope"], ref["mortgages"]["energy_sources"]["not_built"]
    assert set(VOCABS["energy_source"].values) == set(scoped) | set(refused)
    assert pm.method_of("mortgages") == "mortgage" and pm.evic_classes() == {"listed_equity_corporate_bonds",
                                                                              "business_loans_unlisted_equity"}


def test_the_migrations_lists_are_the_reference_files():
    """The migration is self-contained (E25), so it states the lists itself: they must be the reference file's."""
    mig = importlib.import_module("core.db.migrations.versions.pcaf_mortgages_20261025")
    ref = pm.reference()
    assert mig._CLASSES == tuple(c["key"] for c in ref["asset_classes"])
    assert set(mig._SOURCES) == set(ref["mortgages"]["energy_sources"]["scope"])
    assert set(mig._BASES) == set(ref["mortgages"]["energy_bases"])


def test_the_source_is_pinned_and_cited_by_page():
    src = pm.reference()["source"]
    assert re.fullmatch(r"[0-9a-f]{64}", src["sha256"]) and src["url"].startswith("https://carbonaccountingfinancials.com/")
    m = pm.reference()["mortgages"]
    for part in ("definition", "scopes", "attribution", "emissions", "data_quality", "energy_sources", "reporting"):
        assert re.search(r"p{1,2}\. \d", m[part]["ref"]), part


def test_e340_a_column_of_asset_types_is_never_proposed_as_the_pcaf_asset_class():
    """E340: 'commercial_real_estate' is both an asset type and a PCAF class, so a column of asset types was proposed as
    the loan's PCAF asset class from its values alone. The class is proposed only by its column's name."""
    import pandas as pd

    from services.ingest.upload_validation import enrich_specs
    from services.intake import profiling
    from services.intake.catalog import TEMPLATES
    specs = enrich_specs(TEMPLATES["bank_assets"].specs(pd.DataFrame()))
    kinds = pd.DataFrame({"Kind": ["commercial_real_estate"] * 3, "Lat": [48.1, 48.2, 48.3], "Lng": [2.3, 2.4, 2.5]})
    assert "pcaf_asset_class" not in profiling.column_map(profiling.suggest(None, kinds, specs))
    named = pd.DataFrame({"PCAF class": ["mortgages", "commercial_real_estate", "mortgages"]})
    assert profiling.column_map(profiling.suggest(None, named, specs)).get("pcaf_asset_class") == "PCAF class"
