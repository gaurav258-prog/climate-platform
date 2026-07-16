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


def _cal(origin_map, driver="heat_acute"):
    """origin -> (sensitivity, world_share, tier). `driver` is the hazard the coefficient
    was backtested against — the engine will only read THAT hazard."""
    return {o: {"sensitivity": s, "world_share": w, "calibration_tier": t, "hazard_driver": driver}
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
    # publish_gate=False: this asserts the internal world-shock math. With the gate on, a
    # mixed-origin commodity is held and these figures are withheld (see the gate tests).
    r = compute([_commodity("Coffee", plots)], 100_000_000, calibrations=cal,
                publish_gate=False).commodities[0]

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
    cal = {"Coffee": _cal({"BR": (0.45, 0.35, "backtested")}, driver="drought")}
    # publish_gate=False to inspect the world-shock math; with the gate on this book is held.
    r = compute([_commodity("Coffee", plots)], 100_000_000, calibrations=cal,
                publish_gate=False).commodities[0]

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
    cal = {"Coffee": _cal({"BR": (0.45, 0.35, "backtested"), "GT": (0.45, 0.023, "indicative")}, driver="drought")}
    r = compute([_commodity("Coffee", plots)], 100_000_000, calibrations=cal).commodities[0]
    assert r.calibration == "mixed"

    only_bt = [{"spend": 1_000_000, "origin": "BR", "hazards": {"drought": 50.0}}]
    r2 = compute([_commodity("Coffee", only_bt)], 100_000_000, calibrations=cal).commodities[0]
    assert r2.calibration == "backtested"

    only_ind = [{"spend": 1_000_000, "origin": "GT", "hazards": {"drought": 50.0}}]
    r3 = compute([_commodity("Coffee", only_ind)], 100_000_000, calibrations=cal).commodities[0]
    assert r3.calibration == "indicative"


def test_publish_gate_withholds_euro_until_backtested():
    """THE HARD RULE: no € leaves the engine for a crop×origin that hasn't reproduced a
    real event. Exposure and driver stay; the euro figure is withheld, not caveated."""
    plots = [{"spend": 1_000_000, "origin": "ES", "hazards": {"drought": 70.0}}]
    cal = {"Olive oil": _cal({"ES": (0.35, 0.45, "indicative")}, driver="drought")}
    r = compute([_commodity("Olive oil", plots)], 10_000_000, calibrations=cal).commodities[0]

    assert r.status == "held"
    assert r.cogs_at_risk_p50 is None and r.cogs_at_risk_p90 is None
    assert r.market_eur is None and r.price_move_pct is None
    assert "not event-backtested" in r.held_reason
    # exposure is still reported — we withhold the €, not the risk
    assert r.annual_spend_eur == 1_000_000
    assert r.avg_hazard == 70.0 and r.top_hazard == "drought"


def test_gate_keeps_held_euro_out_of_the_headline():
    """Held exposure is reported as SPEND, never summed into the € total."""
    bt = _commodity("Cocoa", [{"spend": 1_000_000, "origin": "CI", "hazards": {"heat_acute": 60.0}}])
    ind = _commodity("Citrus", [{"spend": 5_000_000, "origin": "ES", "hazards": {"heat_acute": 60.0}}])
    cal = {"Cocoa": _cal({"CI": (0.294, 0.45, "backtested")}),
           "Citrus": _cal({"ES": (0.45, 0.03, "indicative")})}
    r = compute([bt, ind], 50_000_000, calibrations=cal)

    assert r.n_held == 1 and r.held_spend_eur == 5_000_000
    assert r.covered_spend_eur == 1_000_000
    published = [c for c in r.commodities if c.status == "scored"]
    assert r.cogs_at_risk_p50 == sum(c.cogs_at_risk_p50 for c in published)   # backtested only


def test_mixed_origin_commodity_is_held_not_blended():
    """One un-backtested origin holds the whole commodity — validated and unvalidated €
    must never be blended into one published figure."""
    plots = [
        {"spend": 1_000_000, "origin": "BR", "hazards": {"drought": 50.0}},
        {"spend": 1_000_000, "origin": "GT", "hazards": {"drought": 50.0}},
    ]
    cal = {"Coffee": _cal({"BR": (0.45, 0.35, "backtested"), "GT": (0.45, 0.023, "indicative")}, driver="drought")}
    r = compute([_commodity("Coffee", plots)], 100_000_000, calibrations=cal).commodities[0]
    assert r.calibration == "mixed" and r.status == "held"
    assert r.cogs_at_risk_p50 is None
    assert "GT" in r.held_reason


def test_gate_can_be_disabled_for_internal_calibration_work_only():
    plots = [{"spend": 1_000_000, "origin": "ES", "hazards": {"drought": 70.0}}]
    cal = {"Olive oil": _cal({"ES": (0.35, 0.45, "indicative")}, driver="drought")}
    r = compute([_commodity("Olive oil", plots)], 10_000_000, calibrations=cal,
                publish_gate=False).commodities[0]
    assert r.status == "scored" and r.cogs_at_risk_p50 > 0


def test_calibrated_coefficient_only_reads_its_backtested_hazard():
    """REGRESSION (real bug, found 2026-07-15). Cocoa's 0.294 was fitted to the 2023/24 HEAT
    event. The engine used to take each plot's WORST hazard — so with heat unscored and
    wildfire at 11.4 it produced yield-shock 3.4% = 0.294 × 11.4, a heat coefficient applied
    to a wildfire score, and badged the result 'backtested'.

    A calibrated coefficient must read ONLY the hazard it was validated against."""
    plots = [{"spend": 1_000_000, "origin": "CI",
              "hazards": {"wildfire": 11.4, "flood": 7.0}}]        # heat_acute NOT scored
    cal = {"Cocoa": _cal({"CI": (0.294, 0.45, "backtested")}, driver="heat_acute")}
    r = compute([_commodity("Cocoa", plots)], 10_000_000, calibrations=cal).commodities[0]

    origin = r.origins[0]
    assert origin["yield_shock_pct"] is None            # NOT 3.4 from wildfire
    assert "heat_acute not scored" in origin["input_required"]
    assert r.status == "held" and r.cogs_at_risk_p50 is None
    # the exposure is still honestly reported
    assert r.annual_spend_eur == 1_000_000 and r.top_hazard == "wildfire"


def test_driver_hazard_used_even_when_another_hazard_scores_higher():
    """The driver is read on its own merits — a higher-scoring unrelated hazard must not
    displace it (nor inflate it)."""
    plots = [{"spend": 1_000_000, "origin": "CI",
              "hazards": {"heat_acute": 74.2, "wildfire": 90.0}}]
    cal = {"Cocoa": _cal({"CI": (0.294, 0.45, "backtested")}, driver="heat_acute")}
    r = compute([_commodity("Cocoa", plots)], 10_000_000, calibrations=cal).commodities[0]
    # 0.294 * 74.2/100 = 21.8% — from heat, not from the higher wildfire score
    assert r.origins[0]["yield_shock_pct"] == 21.8
    assert r.status == "scored"


def test_entirely_unscored_origin_surfaces_instead_of_vanishing():
    """REGRESSION (real, found 2026-07-16 when a re-seed un-snapped Ghana). An origin whose
    plots are ALL unscored used to disappear from the breakdown, because grouping started from
    the scored plots only. The commodity then looked fully 'backtested' on the origins that
    happened to be scored — while half the buyer's spend, and that origin's share of the world
    crop, went silently unrepresented. An unscored origin is a GAP and must be visible."""
    plots = [
        {"spend": 15_000_000, "origin": "CI", "hazards": {"heat_acute": 74.2}},
        {"spend": 15_000_000, "origin": "GH", "hazards": {}},          # entirely unscored
    ]
    cal = {"Cocoa": _cal({"CI": (0.294, 0.45, "backtested"), "GH": (0.294, 0.15, "backtested")},
                         driver="heat_acute")}
    r = compute([_commodity("Cocoa", plots)], 100_000_000, calibrations=cal).commodities[0]

    by = {o["origin"]: o for o in r.origins}
    assert "GH" in by, "an unscored origin vanished from the breakdown"
    assert by["GH"]["yield_shock_pct"] is None
    assert by["GH"]["input_required"]
    # half the world-crop weight is unrepresented, so no € may publish
    assert r.status == "held" and r.cogs_at_risk_p50 is None
