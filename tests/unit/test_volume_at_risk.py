"""The headline is VOLUME at risk — a physical fact — and we never invent a price move.

THE FINDING THIS ENCODES (2026-07-16). The chain used to end in a price prediction, and that
market channel was 97.8% of every euro published. Tested against 440 real crop-years:
    supply shock -> price move : r^2 = 0.018
    stocks -> amplification    : r^2 = 0.041 (empirical exponent 0.23 vs our hardcoded 3.62)
A harvest failure does push price up (64% of 53 real contractions) but HOW MUCH is not
predictable from supply data — the market prices the news long before production is measured.
So the engine states the physical loss and takes the price view from the buyer, or not at all.
"""
from __future__ import annotations

import pytest

from services.intelligence.supply_cogs import compute

CAL = {"Cocoa": {"CI": {"sensitivity": 0.2, "world_share": 0.45,
                        "calibration_tier": "backtested", "hazard_driver": "heat_acute"}}}


def _book(spend=30_000_000, heat=75.0):
    return {"name": "Cocoa", "eudr_covered": True, "elasticity": -0.20, "stock_to_use": 26.4,
            "spend": spend,
            "plots": [{"spend": spend, "origin": "CI", "hazards": {"heat_acute": heat}}]}


def test_headline_is_volume_at_risk_and_needs_no_price_forecast():
    """yield_shock x spend — the volume the buyer paid for that will not arrive."""
    r = compute([_book()], 300_000_000, calibrations=CAL).commodities[0]
    # 0.2 sensitivity x 75/100 heat = 15% of yield
    assert r.yield_shock_pct == pytest.approx(15.0, abs=0.1)
    assert r.volume_at_risk_eur == pytest.approx(0.15 * 30_000_000, rel=0.01)
    assert r.cogs_at_risk_p50 == r.volume_at_risk_eur      # nothing else in the headline


def test_no_price_view_means_no_price_number_at_all():
    """We do not predict price. Absent a buyer view the field is None — not a guess, not 0."""
    r = compute([_book()], 300_000_000, calibrations=CAL).commodities[0]
    assert r.price_scenario_eur is None
    assert r.price_scenario_pct is None


def test_buyer_price_view_is_applied_and_labelled_as_theirs():
    r = compute([_book()], 300_000_000, calibrations=CAL, price_scenario_pct=50.0).commodities[0]
    assert r.price_scenario_pct == 50.0                    # recorded as an input, not a result
    assert r.price_scenario_eur == pytest.approx(0.50 * 30_000_000, rel=0.01)
    # the physical number is untouched by their assumption
    assert r.volume_at_risk_eur == pytest.approx(0.15 * 30_000_000, rel=0.01)
    assert r.cogs_at_risk_p50 == pytest.approx(r.volume_at_risk_eur + r.price_scenario_eur, rel=0.01)


def test_volume_at_risk_scales_with_the_hazard_not_with_market_theory():
    """Double the hazard, double the lost volume. No stocks/elasticity/amplification anywhere."""
    lo = compute([_book(heat=30.0)], 300_000_000, calibrations=CAL).commodities[0]
    hi = compute([_book(heat=60.0)], 300_000_000, calibrations=CAL).commodities[0]
    assert hi.volume_at_risk_eur == pytest.approx(2 * lo.volume_at_risk_eur, rel=0.01)


def test_stocks_no_longer_touch_the_headline():
    """Stocks-to-use drove A(s), which drove 97.8% of the old number. It must now be inert:
    the same crop failure costs the same lost volume whatever the stocks figure says."""
    tight = _book(); tight["stock_to_use"] = 8.0        # A(s) would have exploded here
    loose = _book(); loose["stock_to_use"] = 60.0       # ...and collapsed here
    a = compute([tight], 300_000_000, calibrations=CAL).commodities[0]
    b = compute([loose], 300_000_000, calibrations=CAL).commodities[0]
    assert a.cogs_at_risk_p50 == b.cogs_at_risk_p50


def test_no_fabricated_confidence_band():
    """The old 'P90' was p50 x 1.8 — a decoration, not a distribution. It is gone."""
    r = compute([_book()], 300_000_000, calibrations=CAL)
    assert not hasattr(r, "cogs_at_risk_p90")
    assert not hasattr(r.commodities[0], "cogs_at_risk_p90")


def test_world_shock_survives_as_context_but_drives_nothing():
    """The world supply shock IS validated (cocoa 8.92% vs FAO 8.88%), so we still report it —
    it just no longer produces a price claim."""
    r = compute([_book()], 300_000_000, calibrations=CAL).commodities[0]
    assert r.global_shock_pct > 0                          # still reported
    assert r.volume_at_risk_eur == pytest.approx(0.15 * 30_000_000, rel=0.01)  # unaffected by it
