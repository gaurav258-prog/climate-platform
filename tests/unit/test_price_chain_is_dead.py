"""The published euro must be arithmetically independent of the retired price chain.

WHY THIS EXISTS. stocks-to-use and the amplification curve A(s) were the two parked "known
gaps" — cocoa's 26.4% stocks is hand-entered (ICCO is paywalled) and A(s) has no support in
the data (r^2 = 0.041, empirical exponent 0.23 vs our hardcoded 3.62). They were parked as
things to fix later.

They do not need fixing. They feed the PRICE move, and the product no longer claims one. The
published figure is physical: yield_shock x spend. These tests prove that by construction —
feed the engine absurd values for every price-chain input and assert the euro does not move.

If someone ever re-wires amplification() into compute(), these fail immediately, and that is
the point: a paywalled input that cannot reach a published number is not a gap, but a
paywalled input that CAN reach one is a liability.
"""
from __future__ import annotations

from services.intelligence.supply_cogs import compute

CAL = {"Cocoa": {"CI": {"sensitivity": 0.1995, "world_share": 0.45,
                        "calibration_tier": "backtested", "hazard_driver": "heat_acute"}}}
PLOTS = [{"spend": 1_000_000, "origin": "CI", "hazards": {"heat_acute": 74.2}}]


def _cocoa(**over):
    return {"name": "Cocoa", "eudr_covered": True, "elasticity": -0.20,
            "stock_to_use": 26.4, "spend": 1_000_000, "plots": PLOTS, **over}


def test_stocks_to_use_cannot_move_the_published_euro():
    """Cocoa's 26.4% is hand-entered from a paywalled ICCO figure. It must not be able to
    change what a customer sees."""
    real = compute([_cocoa()], 10_000_000, calibrations=CAL).commodities[0]
    absurd = compute([_cocoa(stock_to_use=99.9)], 10_000_000, calibrations=CAL).commodities[0]
    assert real.volume_at_risk_eur == absurd.volume_at_risk_eur
    assert real.cogs_at_risk_p50 == absurd.cogs_at_risk_p50


def test_elasticity_cannot_move_the_published_euro():
    """Demand elasticity is an assumed per-commodity constant that used to divide straight into
    the price move. It reaches nothing published now."""
    real = compute([_cocoa()], 10_000_000, calibrations=CAL).commodities[0]
    absurd = compute([_cocoa(elasticity=-0.99)], 10_000_000, calibrations=CAL).commodities[0]
    assert real.volume_at_risk_eur == absurd.volume_at_risk_eur


def test_every_price_chain_input_at_once_changes_nothing():
    """Belt and braces: the whole retired chain wrong at the same time, same euro out."""
    real = compute([_cocoa()], 10_000_000, calibrations=CAL).commodities[0]
    absurd = compute([_cocoa(stock_to_use=99.9, elasticity=-0.99)], 10_000_000,
                     calibrations=CAL).commodities[0]
    assert real.volume_at_risk_eur == absurd.volume_at_risk_eur == 148_029.0


def test_amplification_is_not_wired_into_compute():
    """A(s) is kept only so the research scripts still run. If it ever reappears on the
    published path, the euro would start depending on a curve with r^2 = 0.041."""
    import inspect

    from services.intelligence import supply_cogs

    src = inspect.getsource(supply_cogs.compute)
    assert "amplification(" not in src, "amplification() is back on the published path"
    assert "amp" not in inspect.signature(supply_cogs._commodity_risk).parameters
    assert "elasticity" not in inspect.signature(supply_cogs._commodity_risk).parameters
