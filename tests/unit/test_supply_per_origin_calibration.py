"""Per-origin calibration — the world supply shock must follow each origin's share of
WORLD PRODUCTION, not the buyer's spend, and an uncalibrated origin must never borrow
another origin's share.

These are pure-function tests on supply_cogs.compute() — no DB.
"""
from __future__ import annotations

from services.intelligence.supply_cogs import compute


def _commodity(name, plots, elasticity=-0.25, stock=None):
    return {"name": name, "eudr_covered": True, "elasticity": elasticity,
            "stock_to_use": stock, "spend": sum(p["spend"] for p in plots), "plots": plots}


def _cal(origin_map):
    """origin -> (sensitivity, world_share, tier)"""
    return {o: {"sensitivity": s, "world_share": w, "calibration_tier": t, "hazard_driver": "heat_acute"}
            for o, (s, w, t) in origin_map.items()}


def test_single_origin_matches_legacy_exactly():
    """A one-origin book must be byte-identical with and without per-origin calibration —
    the refactor may not move any existing number."""
    plots = [{"spend": 1_000_000, "origin": "ES", "hazards": {"heat_acute": 50.0}}]
    c = _commodity("Olive oil", plots)
    legacy = compute([c], 10_000_000)
    per_origin = compute([c], 10_000_000,
                         calibrations={"Olive oil": _cal({"ES": (None, 0.45, "indicative")})})
    assert legacy.commodities[0].cogs_at_risk_p50 == per_origin.commodities[0].cogs_at_risk_p50


def test_world_shock_follows_production_share_not_spend():
    """THE FIX. Buyer spends 99% in a tiny-share origin and 1% in a dominant-share origin.
    The world price signal must be driven by the DOMINANT origin's hazard, not by where the
    buyer happens to spend."""
    plots = [
        {"spend": 9_900_000, "origin": "PR", "hazards": {"heat_acute": 10.0}},   # 99% of spend, 0.02% of world
        {"spend":   100_000, "origin": "BR", "hazards": {"heat_acute": 90.0}},   # 1% of spend, 35% of world
    ]
    cal = {"Coffee": _cal({"PR": (0.5, 0.0002, "indicative"), "BR": (0.5, 0.35, "backtested")})}
    r = compute([_commodity("Coffee", plots)], 100_000_000, calibrations=cal).commodities[0]

    # world shock = 0.5*0.10*0.0002 + 0.5*0.90*0.35 = 0.00001 + 0.1575 ≈ 15.75%
    assert round(r.global_shock_pct, 1) == 15.8
    by = {o["origin"]: o for o in r.origins}
    assert by["BR"]["global_shock_contribution_pct"] > 15.0     # Brazil dominates the price signal
    assert by["PR"]["global_shock_contribution_pct"] < 0.01     # Puerto Rico is negligible to world price
    # ...but the buyer's OWN exposure still reflects where they actually buy (sourcing channel)
    assert r.yield_shock_pct < 10.0   # spend-weighted, dominated by the low-hazard PR plots


def test_uncalibrated_origin_does_not_borrow_another_origins_share():
    """The Guatemala bug: an origin with no calibration row must contribute NOTHING to the
    world shock and surface the missing input — never silently inherit Brazil's 35% share."""
    plots = [
        {"spend": 1_000_000, "origin": "BR", "hazards": {"drought": 80.0}},
        {"spend": 1_000_000, "origin": "GT", "hazards": {"drought": 80.0}},   # no calibration row
    ]
    cal = {"Coffee": _cal({"BR": (0.45, 0.35, "backtested")})}
    r = compute([_commodity("Coffee", plots)], 100_000_000, calibrations=cal).commodities[0]

    by = {o["origin"]: o for o in r.origins}
    assert by["GT"]["world_share"] is None
    assert by["GT"]["global_shock_contribution_pct"] is None
    assert by["GT"]["input_required"]                       # surfaced, not guessed
    # world shock comes from Brazil alone: 0.45*0.80*0.35 = 12.6%
    assert round(r.global_shock_pct, 1) == 12.6


def test_calibration_tier_is_mixed_when_origins_differ():
    """Validated and unvalidated € must never be silently blended: a book mixing a backtested
    origin with an indicative one is labelled 'mixed'."""
    plots = [
        {"spend": 1_000_000, "origin": "BR", "hazards": {"drought": 50.0}},
        {"spend": 1_000_000, "origin": "GT", "hazards": {"drought": 50.0}},
    ]
    cal = {"Coffee": _cal({"BR": (0.45, 0.35, "backtested"), "GT": (0.45, 0.023, "indicative")})}
    r = compute([_commodity("Coffee", plots)], 100_000_000, calibrations=cal).commodities[0]
    assert r.calibration == "mixed"

    only_bt = [{"spend": 1_000_000, "origin": "BR", "hazards": {"drought": 50.0}}]
    r2 = compute([_commodity("Coffee", only_bt)], 100_000_000, calibrations=cal).commodities[0]
    assert r2.calibration == "backtested"

    only_ind = [{"spend": 1_000_000, "origin": "GT", "hazards": {"drought": 50.0}}]
    r3 = compute([_commodity("Coffee", only_ind)], 100_000_000, calibrations=cal).commodities[0]
    assert r3.calibration == "indicative"
