"""Variance decomposition — pure logic over two bank_tcfd payloads (no DB)."""
from __future__ import annotations

from services.governance.filing_variance import decompose


def _payload(assets, by_hazard, rollup):
    return {"assets": assets, "by_hazard": by_hazard, "rollup": rollup}


def test_identical_payloads_reconcile_to_zero():
    a = [{"asset_id": "1", "asset_name": "A", "value_eur": 100, "headline_score": 40, "headline_bucket": "M"}]
    p = _payload(a, {"flood": {"exposed_value_eur": 0}}, {"total_value_eur": 100, "value_at_risk_eur": 0, "pct_value_at_risk": 0})
    d = decompose(p, p)
    assert d["headline"]["total_value"]["delta"] == 0
    assert d["drivers"]["movers"] == [] and d["drivers"]["new_at_risk"] == []


def test_new_at_risk_and_mover_detected():
    prior = _payload(
        [{"asset_id": "1", "asset_name": "A", "value_eur": 100, "headline_score": 40, "headline_bucket": "M"}],
        {"flood": {"exposed_value_eur": 0}},
        {"total_value_eur": 100, "value_at_risk_eur": 0, "pct_value_at_risk": 0})
    cur = _payload(
        [{"asset_id": "1", "asset_name": "A", "value_eur": 100, "headline_score": 80, "headline_bucket": "VH"}],
        {"flood": {"exposed_value_eur": 100}},
        {"total_value_eur": 100, "value_at_risk_eur": 100, "pct_value_at_risk": 100})
    d = decompose(cur, prior)
    assert d["headline"]["value_at_risk"]["delta"] == 100
    assert d["headline"]["pct_at_risk"]["delta"] == 100
    # asset A newly crossed into at-risk and is a score mover (40→80)
    assert any(x["asset"] == "A" for x in d["drivers"]["new_at_risk"])
    m = d["drivers"]["movers"][0]
    assert m["asset"] == "A" and m["from_score"] == 40 and m["to_score"] == 80 and m["delta"] == 40
    assert next(h for h in d["by_hazard"] if h["hazard"] == "flood")["delta"] == 100


def test_added_and_removed_assets_counted():
    prior = _payload(
        [{"asset_id": "1", "asset_name": "A", "value_eur": 100, "headline_score": 80, "headline_bucket": "VH"}],
        {}, {"total_value_eur": 100, "value_at_risk_eur": 100, "pct_value_at_risk": 100})
    cur = _payload(
        [{"asset_id": "2", "asset_name": "B", "value_eur": 50, "headline_score": 10, "headline_bucket": "L"}],
        {}, {"total_value_eur": 50, "value_at_risk_eur": 0, "pct_value_at_risk": 0})
    d = decompose(cur, prior)
    assert d["counts"]["added"] == 1 and d["counts"]["removed"] == 1
    # A left the book while it was at risk
    assert any(x["asset"] == "A" and x["gone"] for x in d["drivers"]["left_at_risk"])
