"""
Frost hazard scoring — from DAILY minimum temperature (the coffee gap).

The coffee backtest showed the Jul-2021 frost is invisible in monthly means. Frost is a
daily extreme: a single sub-zero night destroys arabica. This scores it from daily-min
2m temperature over the frost season:

  frost_score(0–100) = severity of the season's COLDEST night vs coffee thresholds
      mild/advective risk ≈ +4 °C (screen height ≈ leaf 0 °C) → severe/catastrophic ≈ −2 °C.

Physically, warming REDUCES frost (opposite of heat): forward scenarios ADD the warming
delta to the night temperature, so 2030/2050/2100 frost risk FALLS. v0 uses the season
minimum; frost-day counts + radiative-cooling correction are the documented refinement.
"""
from __future__ import annotations

from .heat_climatology import warming_delta

COFFEE_FROST_MILD, COFFEE_FROST_SEVERE = 4.0, -2.0  # °C at 2m (screen height)


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def frost_score(min_tmin_c: float, scenario: str = "baseline", horizon: str = "current",
                lat: float | None = None) -> float:
    """0–100 frost hazard from the season's coldest night; warming raises the night → less frost
    (AR6 land/latitude-amplified — high-latitude frost falls faster)."""
    if min_tmin_c is None:
        return 0.0
    warming = warming_delta(scenario, horizon, lat)
    t = min_tmin_c + warming
    severity = _clip01((COFFEE_FROST_MILD - t) / (COFFEE_FROST_MILD - COFFEE_FROST_SEVERE))
    return round(100.0 * severity, 1)


def frost_days(daily_tmin_c, threshold: float = 0.0) -> int:
    """Count damaging frost days (Tmin ≤ threshold °C) in a season — the frequency signal."""
    return int(sum(1 for t in daily_tmin_c if t is not None and t <= threshold))
