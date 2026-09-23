"""The pre-submission validation rule sets — pure checks over a frozen-snapshot payload.

No DB: exercises the framework rule functions directly with crafted payloads, so the completeness /
plausibility / tie-out logic and the blocking-vs-warning split are pinned.
"""
from __future__ import annotations

from services.governance.filing_validation import (
    _arrears_finding, _gl_finding, _validate_bank_tcfd, _validate_csrd_e1, _validate_esrs_pack,
    _validate_insurer_solvency, _validate_reit_taxonomy, _validate_sfdr_pai,
)


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


# ── ledger reconciliation gate (closes the "recon tile exists but never blocks anything" gap) ──

def test_gl_no_ledger_uploaded_is_a_warning_not_a_blocker():
    f = _gl_finding({"available": False, "reason": "no_gl_uploaded"})
    assert f["severity"] == "warning" and f["passed"]


def test_gl_within_tolerance_passes_as_blocking_rule():
    f = _gl_finding({"available": True, "reconciled": True, "variance_pct": 0.2, "tolerance_pct": 0.5,
                     "reported_book_eur": 1000000, "gl_book_eur": 998000})
    assert f["severity"] == "blocking" and f["passed"]


def test_gl_out_of_tolerance_actually_blocks_now():
    # This is the exact scenario the independent review flagged: a real, known GL variance that used to
    # sail through submit_for_review unblocked. It must now fail as a blocking rule.
    f = _gl_finding({"available": True, "reconciled": False, "variance_pct": 13.558, "tolerance_pct": 0.5,
                     "reported_book_eur": 4161900000, "gl_book_eur": 3665000000})
    assert f["severity"] == "blocking" and not f["passed"]
    assert "13.558" in f["message"] and "EXCEEDS" in f["message"]


def test_arrears_no_book_uploaded_is_a_warning():
    f = _arrears_finding({"available": False, "reason": "no_arrears_uploaded"})
    assert f["severity"] == "warning" and f["passed"]


def test_arrears_overlay_ran_is_reported_but_never_blocks():
    # Arrears has no fixed tolerance the way GL does — the gate is that it ran, not a pass/fail threshold.
    f = _arrears_finding({"available": True, "summary": {"n_past_due": 4, "n_genuine": 1,
                          "n_not_checked_no_country": 1}})
    assert f["severity"] == "warning" and f["passed"]
    assert "4 past-due" in f["message"] and "no country on record" in f["message"]


# ── coverage extension: REIT / Insurer-Solvency / Agri now get real completeness/plausibility/tie-out
# rulesets, closing the gap the independent review found (only bank_tcfd/sfdr_pai had one) ──

def _good_reit():
    return {"rollup": {"n_properties": 10, "n_scored": 10, "total_value_eur": 100_000_000},
            "art8": {"turnover_kpi": {"total_eur": 5_000_000, "noi_proxy_used": False,
                     "rows": [{"row": "Taxonomy-eligible turnover", "eur": 5_000_000, "pct": 60.0},
                              {"row": "of which Taxonomy-aligned", "eur": 1_000_000, "pct": 12.0},
                              {"row": "Taxonomy-non-eligible turnover", "eur": 2_000_000, "pct": 40.0}]},
                     "capex_kpi": {"status": "computed", "total_eur": 1_200_000}}}


def test_reit_taxonomy_clean_payload_has_no_blockers():
    assert _blocking(_validate_reit_taxonomy(_good_reit())) == []


def test_reit_taxonomy_eligible_plus_non_eligible_must_tie_to_100pct():
    p = _good_reit()
    p["art8"]["turnover_kpi"]["rows"][2]["pct"] = 10.0   # 60 + 10 = 70, not 100
    assert any(f["rule"] == "turnover_eligible_ties_to_100pct" for f in _blocking(_validate_reit_taxonomy(p)))


def test_reit_taxonomy_aligned_cannot_exceed_eligible():
    p = _good_reit()
    p["art8"]["turnover_kpi"]["rows"][1]["pct"] = 90.0   # aligned 90% > eligible 60% — impossible
    assert any(f["rule"] == "aligned_within_eligible" for f in _blocking(_validate_reit_taxonomy(p)))


def test_reit_taxonomy_no_properties_is_blocking():
    p = _good_reit()
    p["rollup"]["n_properties"] = 0
    assert any(f["rule"] == "has_properties" for f in _blocking(_validate_reit_taxonomy(p)))


def _good_solvency():
    return {"rollup": {"n_policies": 50, "n_priced": 50, "total_sum_insured_eur": 500_000_000,
                       "catastrophe": {"available": True, "mean_reconciles": True}},
            "s2601": {"natcat_scr": {"gross_1_in_200_eur": 10_000_000, "net_of_reinsurance_1_in_200_eur": 8_000_000,
                                     "mean_annual_loss_eur": 500_000},
                     "standard_formula_natcat": {"available": True}}}


def test_insurer_solvency_clean_payload_has_no_blockers():
    assert _blocking(_validate_insurer_solvency(_good_solvency())) == []


def test_insurer_solvency_net_cannot_exceed_gross():
    p = _good_solvency()
    p["s2601"]["natcat_scr"]["net_of_reinsurance_1_in_200_eur"] = 15_000_000   # net > gross — impossible
    assert any(f["rule"] == "net_within_gross" for f in _blocking(_validate_insurer_solvency(p)))


def test_insurer_solvency_tail_cannot_be_below_mean():
    p = _good_solvency()
    p["s2601"]["natcat_scr"]["gross_1_in_200_eur"] = 100_000   # below the mean annual loss — impossible
    assert any(f["rule"] == "tail_exceeds_mean" for f in _blocking(_validate_insurer_solvency(p)))


def test_insurer_solvency_engine_mean_reconciliation_failure_blocks():
    # a real internal-engine consistency flag the platform already computes — must surface as blocking
    p = _good_solvency()
    p["rollup"]["catastrophe"]["mean_reconciles"] = False
    assert any(f["rule"] == "cat_mean_reconciles" for f in _blocking(_validate_insurer_solvency(p)))


def test_csrd_e1_missing_entity_name_is_blocking():
    assert any(f["rule"] == "has_entity_identity"
              for f in _blocking(_validate_csrd_e1({"entity": {}, "material_hazards": []})))


def test_csrd_e1_negative_financial_effect_is_blocking():
    payload = {"entity": {"name": "Terra Foods"},
              "material_hazards": [{"hazard": "drought", "label": "Drought",
                                    "upstream": {"cogs_at_risk_eur": -100}}]}
    assert any(f["rule"].startswith("non_negative:") for f in _blocking(_validate_csrd_e1(payload)))


def test_esrs_pack_eudr_plots_must_all_be_accounted_for():
    payload = {"entity": {"name": "Terra Foods"},
              "topics": [{"topic": "E4", "eudr_covered_plots": 10, "deforestation_free": 5,
                         "non_compliant": 1, "geolocation_incomplete": 1, "not_determined": 1}]}  # sums to 8, not 10
    assert any(f["rule"] == "eudr_plots_account_for_covered" for f in _blocking(_validate_esrs_pack(payload)))


def test_esrs_pack_clean_payload_has_no_blockers():
    payload = {"entity": {"name": "Terra Foods"},
              "topics": [{"topic": "E1", "material_hazards": []},
                        {"topic": "E4", "eudr_covered_plots": 10, "deforestation_free": 7,
                         "non_compliant": 1, "geolocation_incomplete": 1, "not_determined": 1}]}
    assert _blocking(_validate_esrs_pack(payload)) == []
