"""S.27.01.01 (ITS (EU) 2023/894) — the nat-cat part bound to the standard formula, cell by cell.

Book: DE windstorm 100m in zone 01, FR 1bn in zone 75, a US risk; premiums stated for windstorm in region 15 (NE US).
Windstorm DE: WSI = 0,0007·0,9·100m = 63 000 → before 1,2·63 000 = 75 600 (R0460). The other-region total R0790 is
1,75·(0,5·1 + 0,5)·5m = 8 750 000 (one region: DIV = 1).
"""
from __future__ import annotations

from datetime import date

import pytest

import services.regspec as R
from services.governance import s2701
from services.governance import solvency2_natcat_tables as T
from services.governance.solvency2_natcat import natcat_scr
from services.regspec.bindings import binding_for

SPEC = R.load(s2701.FAMILY, "its_2023_894")


def test_every_row_and_column_is_bound_in_every_version():
    for v in R.versions(s2701.FAMILY):
        spec = R.load(s2701.FAMILY, v["version"])
        assert R.coverage(spec, binding_for(s2701.FAMILY, spec))["complete"], v["version"]


def test_each_region_row_is_the_printed_region_and_every_region_in_force_has_a_row_or_is_named():
    t = R.template(SPEC, s2701.TID)
    by_id = {r["id"]: r for r in t["rows"]}
    v = T.version(date(2025, 12, 31))
    for peril, rows in s2701.REGION_ROW.items():
        table = T.peril_table(v, peril)
        assert set(rows) == set(table["regions"]), peril                 # every region of the version in force
        for code, row in rows.items():
            r = by_id[row]
            assert r["section"].endswith(peril.title()), (peril, code)
            ours = {w for w in table["regions"][code]["name"].lower().replace("luxembourg", "luxemburg").replace("(", " ").replace(")", " ").split() if len(w) > 4}
            assert ours & set(r["label"].lower().replace("[", " ").split()), (peril, code, r["label"])
    # from 2027 the Regulation adds regions this template prints no row for: named, never dropped
    sf = natcat_scr([{"country": "IE", "sum_insured_eur": 1e8}], ref_date=date(2027, 6, 30))
    assert "Flood IE" in s2701.unrepresented(sf)


def test_the_premium_cells_are_the_undertakings_in_eur():
    cell = R.supplied_cell("insurer_solvency", "S2701.R0750.C0040", date(2025, 12, 31))
    assert cell["unit"] == "EUR" and cell["row"] == "R0750"
    with pytest.raises(R.SpecError):
        R.supplied_cell("insurer_solvency", "S2701.R0460.C0090", date(2025, 12, 31))   # a computed cell


def test_the_grid_fills_the_reportable_cells_from_the_standard_formula():
    supplied = {"S2701.R0750.C0040": 5e6}
    other = s2701.premiums_from_supplied(SPEC, supplied)
    assert other["windstorm"]["by_region"] == {15: 5e6}
    sf = natcat_scr([{"country": "DE", "postal_code": "01067", "sum_insured_eur": 1e8},
                     {"country": "FR", "postal_code": "75001", "sum_insured_eur": 1e9},
                     {"country": "US", "sum_insured_eur": 1e9}], ref_date=date(2025, 12, 31), other_inputs=other)
    g = s2701.grid(SPEC, sf, supplied)
    assert g["R0460"]["C0090"] == 75_600 and g["R0460"]["C0080"] == "A" and g["R0460"]["C0050"] == 100_000_000
    assert g["R0750"]["C0040"] == 5e6 and g["R0790"]["C0090"] == 8_750_000
    assert g["R0820"]["C0090"] == sf["perils"]["windstorm"]["before_eur"]
    assert g["R0010"]["C0030"] == sf["natcat_scr_eur"]
    assert g["R0002"]["C0001"] == "9 – Simplifications not used"          # every risk placed in its zone
    grouped = natcat_scr([{"country": "DE", "sum_insured_eur": 1e8}], ref_date=date(2025, 12, 31))   # no postal code
    assert s2701.grid(SPEC, grouped)["R0002"]["C0001"].split("; ")[0] == "1 – Simplification for the purposes of Article 90b windstorm"
    ok = s2701.reportable(SPEC)
    assert all((r, c) in ok for r, cs in g.items() for c in cs)          # nothing written into a greyed cell
    assert ("R0460", "C0040") not in ok                                   # a region row has no premium cell


def test_the_xbrl_taxonomy_follows_the_reference_date_and_2027_rows_are_not_guessed():
    from services.governance import s2701_xbrl as X
    assert X.taxonomy_for(date(2025, 12, 31))["taxonomy_version"] == "2.8.2"
    assert X.taxonomy_for(date(2027, 12, 31))["taxonomy_version"] == "2.10.0"
    assert X._simplification_codes("4 – Simplification … hail; 1 – Simplification … windstorm") == "1,4"   # BV653: ascending
    assert X._simplification_codes("9 – Simplifications not used") == "9"
    sf = natcat_scr([{"country": "DE", "sum_insured_eur": 1e8}], ref_date=date(2027, 12, 31))
    payload = {"_specs": {s2701.FAMILY: {"version": "its_2023_894"}}, "s2701": {"standard_formula_natcat": sf}}
    with pytest.raises(X.XbrlError, match="Capture the amended template"):
        X.instance(payload, {"lei": "x", "name": "x", "note": "x"})


def test_one_eiopa_data_point_is_one_fact_and_the_cells_sharing_it_agree():
    """A peril's summary row and its 'total after diversification' are one data point in EIOPA's model."""
    import json as _j
    m = _j.load(open("data/reference/eiopa/s2701_xbrl.2.8.2.json"))
    by: dict = {}
    for k, c in m["cells"].items():
        by.setdefault((c["concept"], tuple(sorted(c["dims"].items()))), []).append(k)
    shared = [sorted(v) for v in by.values() if len(v) > 1]
    assert len(shared) == 10 and ["R0020|C0010", "R0820|C0090"] in shared
    sf = natcat_scr([{"country": "DE", "sum_insured_eur": 1e8}, {"country": "FR", "sum_insured_eur": 1e8}], ref_date=date(2025, 12, 31))
    g = s2701.grid(SPEC, sf)
    for pair in shared:
        (r1, c1), (r2, c2) = (x.split("|") for x in pair)
        assert (g.get(r1) or {}).get(c1) == (g.get(r2) or {}).get(c2), pair
