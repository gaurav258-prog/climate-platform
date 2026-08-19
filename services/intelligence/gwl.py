"""Global-warming-level (GWL) trajectory — the physical time axis forward projections interpolate ALONG.

Warming is non-linear in time, and the hazard response is (to first order) linear in warming. So the
physically-correct value at an intermediate year Y is the anchor blend weighted by the GLOBAL WARMING
LEVEL at Y, not by the calendar fraction. This module serves GWL(scenario, year) from the curve built by
scripts/build_gwl.py (anchors = our own CMIP6 ensemble global-mean warming + the observed present-day
node; monotone shape-preserving interpolation between). `weight()` turns that into the blend weight the
horizon resolver uses in place of a calendar fraction.

Scenarios with no CMIP6/SSP mapping (baseline) return None → the caller falls back to calendar-linear,
which is honest there (baseline carries no warming pathway).
"""
from __future__ import annotations

import csv
import os
from functools import lru_cache
from typing import Optional

CSV = "data/gwl/gwl_annual.csv"
# scenarios that ride an SSP warming pathway; baseline/current do not
_SSP_SCENARIOS = {"orderly_1_5c", "disorderly_2c", "hot_house_3_5c"}


@lru_cache(maxsize=1)
def _curve() -> dict:
    """{(scenario, year): gwl_c}. Empty if the curve hasn't been built (caller then falls back)."""
    out: dict = {}
    if not os.path.exists(CSV):
        return out
    with open(CSV) as f:
        for r in csv.DictReader(f):
            out[(r["scenario"], int(r["year"]))] = float(r["gwl_c"])
    return out


def warming_level(scenario: str, year: int) -> Optional[float]:
    """GWL (°C vs 1995-2014) for a scenario at a year, or None when the scenario carries no pathway
    or the curve isn't built. Years outside the built range clamp to the nearest end."""
    if scenario not in _SSP_SCENARIOS:
        return None
    c = _curve()
    if not c:
        return None
    v = c.get((scenario, int(year)))
    if v is not None:
        return v
    years = [y for (s, y) in c if s == scenario]
    if not years:
        return None
    return c[(scenario, min(max(int(year), min(years)), max(years)))]


def weight(scenario: str, lo_year: int, hi_year: int, target_year: int) -> Optional[float]:
    """Blend weight for `target_year` between two anchor years, along the warming curve:
        w = (GWL(target) - GWL(lo)) / (GWL(hi) - GWL(lo))   clamped to [0, 1].
    Returns None when GWL is unavailable (→ caller uses the calendar fraction) or the two anchors carry
    the same warming level (degenerate; caller falls back)."""
    glo = warming_level(scenario, lo_year)
    ghi = warming_level(scenario, hi_year)
    gy = warming_level(scenario, target_year)
    if glo is None or ghi is None or gy is None or ghi == glo:
        return None
    return max(0.0, min(1.0, (gy - glo) / (ghi - glo)))


def available() -> bool:
    return bool(_curve())
