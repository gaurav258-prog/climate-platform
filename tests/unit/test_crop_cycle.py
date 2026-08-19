"""Alternate-bearing decomposition — the tree's biology must not be charged to the weather.

This is the guard against the exact error that made coffee's calibration ~7x over-attributed:
handing a raw -19.4% year to a drought coefficient when ~14pp of it was the biennial cycle.
"""
from __future__ import annotations

from ml.features.crop_cycle import (
    MIN_YEARS,
    climate_attributable_pct,
    decompose,
)


def _alternating(base=1000.0, n=24, amp=0.35, start_year=2000, shock_year=None, shock=0.0):
    """A synthetic perfectly alternate-bearing series, optionally with one climate shock."""
    out = {}
    for i in range(n):
        y = start_year + i
        v = base * (1 + amp if i % 2 == 0 else 1 - amp)
        if shock_year is not None and y == shock_year:
            v *= (1 + shock)
        out[y] = v
    return out


def test_pure_cycle_has_no_climate_signal():
    """A perfectly alternating series with no weather in it must yield ~0% climate anomaly —
    every swing is explained by the cycle."""
    d = decompose(_alternating())
    assert d["alternate_bearing"] is True
    assert d["phi"] < -0.2
    # sample a mid-series OFF-year: raw YoY is a huge drop, climate is ~nothing
    t = d["years"][2011]
    assert t["raw_yoy_pct"] < -40           # looks catastrophic
    assert abs(t["climate_pct"]) < 2        # ...but it is purely the tree alternating
    assert d["phi"] < -0.9                  # a perfect cycle is recovered as phi ~ -1


def test_shock_on_top_of_a_cycle_is_recovered():
    """An extra -30% climate shock landing on an off-year must be recovered as roughly -30%,
    not as the much larger raw drop."""
    d = decompose(_alternating(shock_year=2013, shock=-0.30), 2013)
    t = d["target"]
    assert t["raw_yoy_pct"] < -50                     # raw conflates cycle + shock
    assert -42 < t["climate_pct"] < -18               # recovered near the true -30%
    assert t["climate_pct"] > t["raw_yoy_pct"]        # climate share is smaller than raw


def test_non_cyclical_crop_keeps_its_signal():
    """A crop with no cycle (cocoa) must not have its climate signal shrunk away."""
    series = {2000 + i: 1000.0 * (1.02 ** i) for i in range(20)}   # steady growth, no cycle
    series[2015] *= 0.75                                            # a real -25% shock
    d = decompose(series, 2015)
    # NOTE a single large shock does induce a mild apparent phi (a drop followed by recovery
    # looks a little like alternation) — with only 20 points it reads ~-0.3. That is a known,
    # CONSERVATIVE artifact: it charges part of the shock to "cycle", shrinking the climate
    # share rather than inflating it. Real panels with several decades wash it out.
    assert -32 < d["target"]["climate_pct"] < -15      # the shock survives largely intact


def test_trend_is_removed_so_growth_is_not_a_climate_signal():
    """A cleanly growing series has no climate anomaly — growth is trend, not weather."""
    d = decompose({2000 + i: 1000.0 * (1.05 ** i) for i in range(20)})
    for y, v in d["years"].items():
        assert abs(v["climate_pct"]) < 8, f"{y} invented a climate signal from pure trend"


def test_refuses_to_characterise_a_cycle_without_history():
    """Under MIN_YEARS we make no claim at all rather than fit noise."""
    short = {2018 + i: 1000.0 for i in range(MIN_YEARS - 1)}
    d = decompose(short)
    assert d["phi"] is None and d["alternate_bearing"] is False
    assert "need >=" in d["note"]
    assert climate_attributable_pct(short, 2020) is None


def test_collapse_year_does_not_drag_the_trend_down_and_hide_itself():
    """The trend uses a rolling MEDIAN, so a single collapse cannot pull the baseline down to
    meet it — which would shrink the very signal we are trying to measure."""
    series = {2000 + i: 1000.0 for i in range(20)}
    series[2010] = 400.0                       # -60% collapse
    d = decompose(series, 2010)
    assert d["target"]["climate_pct"] < -45    # still reads as a major shock
