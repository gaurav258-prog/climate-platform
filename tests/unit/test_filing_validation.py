"""The pre-submission validation rule sets — pure checks over a frozen-snapshot payload.

No DB: exercises the framework rule functions directly with crafted payloads, so the completeness /
plausibility / tie-out logic and the blocking-vs-warning split are pinned.
"""
from __future__ import annotations

from services.governance.filing_validation import _validate_bank_tcfd, _validate_sfdr_pai


def _blocking(findings):
    return [f for f in findings if f["severity"] == "blocking" and not f["passed"]]


def _good_bank():
    return {
        "rollup": {"n_assets": 10, "n_scored": 10, "total_value_eur": 1000,
                   "value_at_risk_eur": 300, "pct_value_at_risk": 30.0,
                   "by_bucket": {"L": {"value_eur": 700}, "H": {"value_eur": 200}, "VH": {"value_eur": 100}}},
        "by_hazard": {"flood": {"exposed_value_eur": 300}},
        "financed_emissions_tco2e": {"scope1": 10, "scope2": 5, "scope3": 50},
    }


def test_bank_clean_payload_has_no_blockers():
    findings = _validate_bank_tcfd(_good_bank())
    assert _blocking(findings) == []


def test_bank_nothing_scored_is_blocking():
    p = _good_bank()
    p["rollup"]["n_scored"] = 0
    msgs = [f["rule"] for f in _blocking(_validate_bank_tcfd(p))]
    assert "some_scored" in msgs


def test_bank_partial_coverage_is_a_warning_not_a_blocker():
    p = _good_bank()
    p["rollup"]["n_scored"] = 7   # 7/10
    findings = _validate_bank_tcfd(p)
    assert _blocking(findings) == []                      # still submittable
    cov = next(f for f in findings if f["rule"] == "full_coverage")
    assert cov["severity"] == "warning" and not cov["passed"]


def test_bank_buckets_not_reconciling_is_blocking():
    p = _good_bank()
    p["rollup"]["by_bucket"]["L"]["value_eur"] = 999999   # break the tie-out
    assert any(f["rule"] == "buckets_reconcile" for f in _blocking(_validate_bank_tcfd(p)))


def test_bank_hazard_exposure_exceeding_book_is_flagged():
    p = _good_bank()
    p["by_hazard"]["flood"]["exposed_value_eur"] = 10_000   # > book
    f = next(x for x in _validate_bank_tcfd(p) if x["rule"] == "hazard_within_book:flood")
    assert not f["passed"]


def test_sfdr_missing_manager_identity_is_blocking():
    payload = {
        "entity": {"positions": 20, "total_value_eur": 5000},
        "filing_readiness": {"ready_to_file": False, "missing": ["manager LEI", "narrative: policies"]},
        "coverage_summary": {"mandatory_indicators": 14, "computed": 14, "emissions_coverage_pct": 80},
        "narratives": {"missing": []}, "per_fund": [],
    }
    assert any(f["rule"] == "filing_identity" for f in _blocking(_validate_sfdr_pai(payload)))


def test_sfdr_ready_statement_has_no_blockers():
    payload = {
        "entity": {"positions": 20, "total_value_eur": 5000},
        "filing_readiness": {"ready_to_file": True, "missing": []},
        "coverage_summary": {"mandatory_indicators": 14, "computed": 14, "emissions_coverage_pct": 80},
        "narratives": {"missing": []}, "per_fund": [],
    }
    assert _blocking(_validate_sfdr_pai(payload)) == []


def test_sfdr_build_error_is_a_single_blocker():
    findings = _validate_sfdr_pai({"error": "manager has no positions to report on"})
    assert len(_blocking(findings)) == 1
