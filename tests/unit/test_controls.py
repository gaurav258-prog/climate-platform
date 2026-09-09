"""Reporting control register: the register is complete and sector-free; the evaluators judge evidence honestly."""
from datetime import datetime, timedelta, timezone

from services.governance import controls as C


def test_register_is_complete_and_every_rule_is_evaluable():
    reg = C.register()
    ids = [c["id"] for c in reg["controls"]]
    assert len(ids) == len(set(ids)) >= 15
    for c in reg["controls"]:
        assert c["category"] in reg["categories"] and c["type"] in ("preventive", "detective")
        assert c["objective"] and c["evidence"] and c["anchor"] and c["rules"]
        for w in ("bank", "insurer", "credit institution"):
            assert w not in c["objective"].lower()
    assert C.control("C-INT-01")["rules"] == ["snapshot_frozen"] and C.control("nope") is None


def _ev(**kw):
    base = {"filings": [], "findings": {}, "readiness": {}, "feeds": [], "models": [], "gate": 0.40, "breaches": [], "last_scan": None, "obligations": [], "org_type": "bank"}
    return {**base, **kw}


def test_findings_control_fails_on_any_failed_item_and_is_na_without_filings():
    c = C.control("C-TIE-01")
    assert C.evaluate(_ev(), c)[0] == "not_applicable"
    ev = _ev(findings={"buckets_reconcile": [{"filing_id": "f", "framework": "bank_tcfd", "period": "FY25", "passed": True, "severity": "blocking", "message": "ok"}],
                       "var_ties_to_buckets": [{"filing_id": "f", "framework": "bank_tcfd", "period": "FY25", "passed": False, "severity": "warning", "message": "VaR differs"}]})
    out, n, nf, detail = C.evaluate(ev, c)
    assert (out, n, nf) == ("fail", 2, 1) and detail[0]["message"] == "VaR differs"


def test_release_approval_and_readiness_controls():
    c = C.control("C-GOV-01")
    ev = _ev(filings=[{"filing_id": "a", "framework": "x", "period_label": "FY25", "status": "accepted", "approval_request_id": "r1"},
                      {"filing_id": "b", "framework": "x", "period_label": "FY24", "status": "submitted", "approval_request_id": None}],
             readiness={"second_approver": {"key": "second_approver", "label": "A second approver exists", "ok": True}})
    assert C.evaluate(ev, c)[0] == "fail"
    ev["filings"][1]["approval_request_id"] = "r2"
    assert C.evaluate(ev, c)[0] == "pass"
    assert C.evaluate(_ev(readiness={"identity": {"key": "identity", "label": "id", "ok": False, "hint": "set LEI"}}), C.control("C-GOV-02"))[0] == "fail"
    assert C.evaluate(_ev(), C.control("C-GOV-02"))[0] == "not_applicable"


def test_models_breaches_scan_and_obligations():
    ev = _ev(models=[{"hazard_type": "flood", "model_version": "v1", "r2_oos": 0.35, "is_active": True}, {"hazard_type": "heat", "model_version": "v2", "r2_oos": None, "is_active": True}])
    out, n, nf, detail = C.evaluate(ev, C.control("C-MOD-01"))
    assert (out, n, nf) == ("fail", 2, 1) and detail[0]["hazard"] == "flood"      # a screening model (no r²) is allowed as screening
    now = datetime.now(timezone.utc)
    ev = _ev(breaches=[{"framework": "x", "kri_key": "k", "label": "L", "severity": "red", "onset_at": now - timedelta(days=9), "acknowledged_at": None},
                       {"framework": "x", "kri_key": "k2", "label": "L2", "severity": "red", "onset_at": now - timedelta(days=2), "acknowledged_at": None}])
    assert C.evaluate(ev, C.control("C-APP-01"))[:3] == ("fail", 2, 1)
    assert C.evaluate(_ev(last_scan=now - timedelta(days=3)), C.control("C-REG-01"))[0] == "pass"
    assert C.evaluate(_ev(last_scan=now - timedelta(days=9)), C.control("C-REG-01"))[0] == "fail"
    assert C.evaluate(_ev(last_scan=None), C.control("C-REG-01"))[0] == "fail"
    ob = [{"framework": "x", "period_label": "FY25", "due_date": now.date() - timedelta(days=1), "met": False}]
    assert C.evaluate(_ev(obligations=ob), C.control("C-REG-02"))[0] == "fail"
    ob[0]["met"] = True
    assert C.evaluate(_ev(obligations=ob), C.control("C-REG-02"))[0] == "pass"


def test_csv_export_has_one_row_per_control():
    v = {"window_days": 90, "controls": [{**c, "category_label": c["category"], "last": None, "pass_rate_pct": None, "n_tests": 0, "last_fail": None, "owner": None, "review_by": None} for c in C.register()["controls"]]}
    lines = C.register_csv(v).decode("utf-8").splitlines()
    assert len(lines) == 1 + len(C.register()["controls"]) and lines[0].startswith("Control,Label,Category")
