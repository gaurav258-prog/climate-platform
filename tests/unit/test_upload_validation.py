"""Upload validation — the check-before-save foundation (services.ingest.upload_validation)."""
import io

import pandas as pd

from services.ingest.upload_validation import parse_table, validate_table

SPECS = [
    {"name": "asset_name", "required": True, "label": "Asset name", "kind": "text"},
    {"name": "latitude", "required": True, "label": "Latitude", "kind": "lat"},
    {"name": "longitude", "required": True, "label": "Longitude", "kind": "lon"},
    {"name": "appraised_value_eur", "required": True, "label": "Appraised value (EUR)", "kind": "money"},
    {"name": "loan_origination_date", "required": False, "label": "Loan origination date", "kind": "date"},
]


def _df(rows):
    return pd.DataFrame(rows)


def test_all_valid_rows_pass():
    rep = validate_table(_df([
        {"asset_name": "Tower 1", "latitude": 50.1, "longitude": 8.6, "appraised_value_eur": 1000000},
        {"asset_name": "Tower 2", "latitude": 48.2, "longitude": 2.3, "appraised_value_eur": 500000, "loan_origination_date": "2022-03-01"},
    ]), SPECS)
    assert rep["ok"] and rep["n_valid"] == 2 and rep["n_error"] == 0 and rep["errors"] == []


def test_missing_required_column_short_circuits():
    rep = validate_table(_df([{"latitude": 50.1, "longitude": 8.6, "appraised_value_eur": 1}]), SPECS)
    assert rep["ok"] is False and "asset_name" in rep["missing_columns"]


def test_per_row_problems_with_reasons_and_spreadsheet_row_numbers():
    rep = validate_table(_df([
        {"asset_name": "OK", "latitude": 50.1, "longitude": 8.6, "appraised_value_eur": 1000000},   # row 2
        {"asset_name": "BadCoord", "latitude": None, "longitude": 8.6, "appraised_value_eur": 1000000},  # row 3
        {"asset_name": "BadValue", "latitude": 50.1, "longitude": 8.6, "appraised_value_eur": "n/a"},     # row 4
        {"asset_name": "BadDate", "latitude": 50.1, "longitude": 8.6, "appraised_value_eur": 1, "loan_origination_date": "03/2022"},  # row 5
        {"asset_name": "OutOfRange", "latitude": 200, "longitude": 8.6, "appraised_value_eur": 1},        # row 6
    ]), SPECS)
    assert rep["n_valid"] == 1 and rep["n_error"] == 4
    by_row = {e["row"]: " ".join(e["problems"]) for e in rep["errors"]}
    assert "Latitude is required" in by_row[3]
    assert "Appraised value (EUR) must be a number" in by_row[4]
    assert "YYYY-MM-DD" in by_row[5]
    assert "between −90 and 90" in by_row[6]


def test_parse_csv_and_excel_roundtrip():
    df = _df([{"asset_name": "T", "latitude": 1.0, "longitude": 2.0, "appraised_value_eur": 5}])
    csv = df.to_csv(index=False).encode()
    assert list(parse_table(csv, "book.csv").columns) == list(df.columns)
    xbuf = io.BytesIO(); df.to_excel(xbuf, index=False)
    assert parse_table(xbuf.getvalue(), "book.xlsx").shape == df.shape


def test_unsupported_file_type_raises():
    try:
        parse_table(b"x", "book.pdf")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "CSV or Excel" in str(e)
