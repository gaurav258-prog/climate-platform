"""Intake controls: receipt, transformation tie-out, gate, landing (services/ingest/batch_controls.py)."""
import pandas as pd

from services.ingest import batch_controls as bc
from services.ingest.upload_validation import enrich_specs, validate_table

SPECS = enrich_specs([
    {"name": "asset_name", "required": True},
    {"name": "latitude", "required": True},
    {"name": "longitude", "required": True},
    {"name": "appraised_value_eur", "required": True},
])


def _df(rows):
    return pd.DataFrame(rows)


def _run(rows, declared=None, duplicate_of=None):
    df = _df(rows)
    rep = validate_table(df, SPECS)
    norm = bc.normalise_rows(rep["valid_rows"], SPECS)
    rc = bc.receipt_check(df, declared=declared, duplicate_of=duplicate_of)
    tr = bc.transformation_check(df, SPECS, rep, norm, value_field="appraised_value_eur")
    return df, rep, norm, rc, tr, bc.evaluate_gate(rc, tr, rep["n_valid"])


GOOD = [{"asset_name": f"A{i}", "latitude": 48.0 + i / 10, "longitude": 2.0, "appraised_value_eur": 1_000_000} for i in range(4)]


def test_parse_money_strips_thousands_and_never_guesses_a_decimal_comma():
    assert bc.parse_money("1,250,000") == 1_250_000.0
    assert bc.parse_money(" 1 250 000 ") == 1_250_000.0
    assert bc.parse_money("1.234,5") is None       # ambiguous → unparseable, not silently misread
    assert bc.parse_money("") is None and bc.parse_money(None) is None and bc.parse_money(float("nan")) is None


def test_clean_file_passes_every_gate():
    _, rep, _, rc, tr, gate = _run(GOOD)
    assert rc["status"] == "pass" and tr["status"] == "pass" and gate["status"] == "pass"
    assert rep["n_valid"] == 4


def test_normalisation_makes_validated_values_the_values_the_engine_reads():
    rows = [{"asset_name": "X", "latitude": "48.1", "longitude": "2.3", "appraised_value_eur": "1,250,000"}]
    _, rep, norm, _, tr, _ = _run(rows)
    assert rep["n_valid"] == 1                         # the validator accepts the thousands separator…
    assert norm[0]["appraised_value_eur"] == 1_250_000.0   # …and the engine now receives a real number
    assert isinstance(norm[0]["latitude"], float)
    assert tr["tie_outs"][0]["status"] == "pass"


def test_declared_row_count_and_control_total_mismatch_fail_the_receipt():
    _, _, _, rc, _, gate = _run(GOOD, declared={"row_count": 5, "control_totals": {"appraised_value_eur": 5_000_000}})
    failed = {c["check"] for c in rc["checks"] if c["status"] == "fail"}
    assert failed == {"declared_row_count", "declared_total:appraised_value_eur"}
    assert gate["status"] == "needs_signoff"


def test_declared_totals_that_match_pass():
    _, _, _, rc, _, gate = _run(GOOD, declared={"row_count": 4, "control_totals": {"appraised_value_eur": 4_000_000}})
    assert rc["status"] == "pass" and gate["status"] == "pass"


def test_control_total_on_missing_column_or_unreadable_cells_fails():
    _, _, _, rc, _, _ = _run(GOOD, declared={"control_totals": {"nope": 1}})
    assert next(c for c in rc["checks"] if c["check"] == "declared_total:nope")["status"] == "fail"
    rows = GOOD + [{"asset_name": "B", "latitude": 48, "longitude": 2, "appraised_value_eur": "n/a"}]
    _, _, _, rc2, _, _ = _run(rows, declared={"control_totals": {"appraised_value_eur": 4_000_000}})
    assert next(c for c in rc2["checks"] if c["check"].startswith("declared_total"))["status"] == "fail"


def test_exact_duplicate_rows_and_repeat_file_need_signoff():
    _, _, _, rc, _, gate = _run(GOOD + [GOOD[0]])
    assert next(c for c in rc["checks"] if c["check"] == "no_duplicate_rows")["status"] == "fail"
    assert gate["status"] == "needs_signoff"
    _, _, _, rc2, _, gate2 = _run(GOOD, duplicate_of={"imported_at": "2026-09-01"})
    assert next(c for c in rc2["checks"] if c["check"] == "file_not_already_imported")["status"] == "fail"
    assert gate2["status"] == "needs_signoff"


def test_rejected_value_is_stated_and_over_limit_needs_signoff():
    rows = GOOD + [{"asset_name": "BAD", "latitude": 999, "longitude": 2, "appraised_value_eur": 9_000_000}]
    _, rep, _, _, tr, gate = _run(rows)
    assert rep["n_error"] == 1
    assert tr["excluded"]["n_rows"] == 1 and tr["excluded"]["value"] == 9_000_000.0
    assert tr["excluded"]["pct_value"] > 60                  # 9m of 13m — a reviewer must see this
    assert gate["status"] == "needs_signoff"
    assert any("rejected" in r for r in gate["reasons"])
    t = tr["tie_outs"][0]
    assert abs(t["raw_total"] - (t["accepted_total"] + t["rejected_total"])) < 1e-6   # the tie-out holds


def test_no_valid_rows_is_blocked_not_signoffable():
    rows = [{"asset_name": "BAD", "latitude": 999, "longitude": 2, "appraised_value_eur": 1}]
    assert _run(rows)[-1]["status"] == "blocked"


def test_landing_reports_rows_dropped_after_validation():
    ok = bc.landing_check(n_valid=4, n_landed=4, value_valid=4e6, value_landed=4e6)
    assert ok["status"] == "pass"
    bad = bc.landing_check(n_valid=4, n_landed=3, value_valid=4e6, value_landed=3e6)
    assert bad["status"] == "attention" and bad["n_dropped_after_validation"] == 1
