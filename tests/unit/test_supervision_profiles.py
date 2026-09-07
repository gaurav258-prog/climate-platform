"""Supervision is configuration: profiles resolve from JSON, metrics are sector-agnostic adapters."""
import pytest

from services.supervision import metrics as M
from services.supervision.profiles import (
    all_permission_codes,
    profile_ids,
    registry,
    resolve,
    sector_config,
)


def test_registry_is_complete_and_every_adapter_exists():
    reg = registry()
    assert "banking_supervisor" in profile_ids() and reg["cycle"][0] == "collect"
    for sec, s in reg["sectors"].items():
        assert s["frameworks"] and s["region_unit"] and s["metrics"], sec
        for m in s["metrics"]:
            assert m["adapter"] in M.ADAPTERS, f"{sec}.{m['id']} → {m['adapter']}"
    for pid, p in reg["profiles"].items():
        assert all(sec in reg["sectors"] for sec in p["sectors"]), pid
    assert "supervisor.sites.view" in all_permission_codes()


def test_resolve_applies_overrides_without_touching_the_registry():
    base = resolve("banking_supervisor")
    assert list(base["sectors"]) == ["bank"] and base["default_scenario"] == "baseline"
    ov = resolve(None, {"profile": "insurance_supervisor", "default_horizon": "2030",
                        "thresholds": {"insurer": {"high_risk_share_pct": {"watch_above": 10}}}})
    assert list(ov["sectors"]) == ["insurer"] and ov["default_horizon"] == "2030"
    m = next(x for x in ov["sectors"]["insurer"]["metrics"] if x["id"] == "high_risk_share_pct")
    assert m["watch_above"] == 10
    again = resolve("insurance_supervisor")
    assert next(x for x in again["sectors"]["insurer"]["metrics"] if x["id"] == "high_risk_share_pct")["watch_above"] == 25
    assert sector_config(base, "insurer") is None and sector_config(base, "bank")["book_noun"] == "financed assets"
    with pytest.raises(KeyError):
        resolve("no_such_profile")


def test_metrics_are_bucket_consistent_and_sector_agnostic():
    pts = [{"value_eur": 100, "score": 80, "hazard": "flood", "lat": 49.45, "lon": 11.08},
           {"value_eur": 100, "score": 55, "hazard": "flood", "lat": 40.85, "lon": 14.27},
           {"value_eur": 100, "score": 10, "hazard": "drought", "lat": 40.85, "lon": 14.27},
           {"value_eur": 100, "score": None, "hazard": None, "lat": 5.6, "lon": -0.2}]
    spec = registry()["sectors"]["bank"]["metrics"]
    v = M.compute(spec, pts)
    assert v["book_value_eur"] == 400 and v["money_at_high_risk_eur"] == 200 and v["high_risk_share_pct"] == 50.0
    assert v["top_hazard_concentration_pct"] == 50.0 and v["scored_coverage_pct"] == 75.0
    assert v["top_region_concentration_pct"] == 50.0      # Naples twice
    hr = next(m for m in spec if m["id"] == "high_risk_share_pct")
    assert M.flag(hr, 50.0) == "act" and M.flag(hr, 30.0) == "watch" and M.flag(hr, 10.0) == "ok" and M.flag(hr, None) == "na"
    assert M.compute(spec, []) == {k: (0 if k in ("book_value_eur", "money_at_high_risk_eur") else None) for k in v}
    with pytest.raises(KeyError):
        M.compute([{"id": "x", "adapter": "portfolio.nope"}], pts)
