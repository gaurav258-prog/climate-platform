"""Intake: header mapping suggestions, number parsing, validate-before-save shape, cells from rows."""
from services.supervision.intake import _num, cells_from_rows, map_rows, suggest_mapping
from services.supervision.profiles import registry

BANK = registry()["sectors"]["bank"]["intake"]


def test_suggest_mapping_matches_synonyms_without_reusing_a_column():
    cols = ["Instrument ID", "Debtor name", "NACE", "Outstanding nominal amount", "Final maturity", "Protection country", "Protection NUTS3", "Postal code"]
    m = suggest_mapping(cols, BANK["granular"]["row_fields"])
    assert m["instrument_id"] == "Instrument ID" and m["counterparty_name"] == "Debtor name" and m["nace_section"] == "NACE"
    assert m["outstanding_eur"] == "Outstanding nominal amount" and m["maturity_date"] == "Final maturity"
    assert m["collateral_country"] == "Protection country" and m["collateral_nuts3"] == "Protection NUTS3" and m["collateral_postcode"] == "Postal code"
    assert len({v for v in m.values() if v}) == len([v for v in m.values() if v])


def test_numbers_in_european_and_english_formats():
    assert _num("1.234.567,89") == 1234567.89 and _num("1,234,567.89") == 1234567.89 and _num("€ 12,5") == 12.5 and _num("x") is None
    assert _num("1.000.000") == 1000000 and _num("1,000,000") == 1000000 and _num("12.5") == 12.5


def test_map_rows_validates_before_save_and_builds_cells():
    csv = b"Geography,Sector,Gross carrying amount,of which sensitive\nES,C,1000,400\nES,C,500,100\nDE,K,abc,10\nFR,,20,5\n"
    fields = BANK["submission"]["cell_fields"]
    m = suggest_mapping(["Geography", "Sector", "Gross carrying amount", "of which sensitive"], fields)
    assert m["gross_carrying_amount_eur"] == "Gross carrying amount" and m["sensitive_physical_eur"] == "of which sensitive"
    rep = map_rows(csv, "t5.csv", fields, m)
    assert rep["n_total"] == 4 and rep["n_valid"] == 2 and rep["n_error"] == 2 and rep["ok"]
    assert any("not a number" in p for e in rep["errors"] for p in e["problems"]) and any("missing" in p for e in rep["errors"] for p in e["problems"])
    cells = cells_from_rows(rep["rows"])
    assert cells["ES|C"]["gross_carrying_amount_eur"] == 1500 and cells["ES|C"]["sensitive_physical_eur"] == 500
    rep2 = map_rows(csv, "t5.csv", fields, {**m, "gross_carrying_amount_eur": None})
    assert not rep2["ok"] and rep2["missing_required"] == ["gross_carrying_amount_eur"]


def test_a_row_problem_is_a_message_code_counted_over_every_row():
    # UI standard (2026-10-16): each problem carries its catalogue code, field and value; its words come from the
    # catalogue in the field's own label; problem_types counts every row by code and field, with the pop-up text.
    csv = b"Geography,Sector,Gross carrying amount,of which sensitive\nES,C,1000,400\nDE,K,abc,10\nFR,,20,5\nIT,,30,5\n"
    fields = BANK["submission"]["cell_fields"]
    m = suggest_mapping(["Geography", "Sector", "Gross carrying amount", "of which sensitive"], fields)
    rep = map_rows(csv, "t5.csv", fields, m)
    bad = next(e for e in rep["errors"] if e["row"] == 3)
    assert [i["code"] for i in bad["issues"]] == ["supervision.intake.row.not_a_number"]      # unreadable, not also 'missing'
    assert bad["issues"][0]["value"] == "abc" and bad["problems"] == ["Gross carrying amount (€): not a number"]
    by = {(t["code"], t["field"]): t for t in rep["problem_types"]}
    assert by[("supervision.intake.row.missing", "sector")]["count"] == 2 and by[("supervision.intake.row.missing", "sector")]["rows"] == [4, 5]
    assert all(t["detail"]["what"] for t in rep["problem_types"]) and rep["problem_types"][0]["count"] == 2
