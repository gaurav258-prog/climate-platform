"""Variance decomposition — pure logic over two bank_tcfd payloads (no DB)."""
from __future__ import annotations

from services.governance.filing_variance import decompose


def _payload(assets, by_hazard, rollup, level=50.0):
    """A frozen payload with the method it was computed on: the stated at-risk level (a test value)."""
    used = [] if level is None else [{"key": "method.at_risk_level", "member": None, "value": level}]
    return {"assets": assets, "by_hazard": by_hazard, "rollup": rollup, "method": {"used": used, "gaps": []}}


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


def test_each_side_uses_its_own_stated_level_and_a_change_is_reported():
    a = [{"asset_id": "1", "asset_name": "A", "value_eur": 100, "headline_score": 60, "headline_bucket": "H"}]
    prior = _payload(a, {}, {}, level=70.0)          # below the prior level
    cur = _payload(a, {}, {}, level=50.0)            # same score, a lower stated level now
    d = decompose(cur, prior)
    assert d["at_risk_level"] == {"now": 50.0, "prior": 70.0, "changed": True}
    assert d["headline"]["value_at_risk"] == {"now": 100, "prior": 0, "delta": 100}
    assert d["drivers"]["movers"] == []              # the score did not move — the method did


def test_a_side_without_a_stated_level_is_a_gap_never_zero():
    a = [{"asset_id": "1", "asset_name": "A", "value_eur": 100, "headline_score": 80, "headline_bucket": "VH"}]
    d = decompose(_payload(a, {}, {}), _payload(a, {}, {}, level=None))
    assert d["headline"]["value_at_risk"] == {"now": 100, "prior": None, "delta": None}
    assert d["headline"]["pct_at_risk"]["delta"] is None and "method.at_risk_level" in d["at_risk_level"]["gap"]
    assert d["drivers"]["new_at_risk"] == [] and d["drivers"]["left_at_risk"] == []
