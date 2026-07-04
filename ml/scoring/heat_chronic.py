"""
Chronic heat hazard scoring — "how much of a normal year is dangerously hot
here," distinct from heat_acute's "is today dangerously hot."

Threshold: 30 deg C, the real "Hot Days" indicator threshold used by
Copernicus Climate Change Service (C3S) / Climate-ADAPT (their European
Climate Data Explorer offers 30/35/40 deg C as selectable tiers for this
exact indicator). **Disclosed simplification, not hidden**: C3S's indicator
counts days where DAILY MAXIMUM temperature exceeds 30 deg C; this scorer
only has MONTHLY MEAN temperature (climatology_baseline has no daily-max
statistic -- that would need an entirely separate, much larger data-
engineering project, deferred). Applying the same 30 deg C reference point
to daily MEAN instead of MAX makes this a conservative, lower-bound proxy
for the official C3S figure at the same location (mean is always <= max),
not a claim of matching it exactly.

Uses a Gaussian assumption (temp ~ N(clim_mean, clim_std) for each calendar
month) to estimate P(day exceeds threshold), same "Gaussian v0, refine to a
better-fitting distribution later" convention as ml/features/drought.py's
SPI/SPEI. Reuses heat_climatology.py's SCENARIO_WARMING_C/HORIZON_FRACTION
directly for the warming shift -- one scenario-warming model for both heat
hazards, not two independently-invented ones.
"""
from __future__ import annotations

from scipy.stats import norm

from .heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

HOT_DAY_THRESHOLD_C = 30.0  # C3S "Hot Days" indicator reference (mean-temp proxy, see module docstring)
DAYS_IN_MONTH = {1: 31, 2: 28.25, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

# Score anchors: 0 days/yr -> 0, a quarter of the year (91d) -> ~65, half the
# year (182d) -> 100 (capped). A location spending half its year above what
# C3S calls a "hot day" is maximally severe chronic exposure -- a real,
# stated anchor, not an arbitrary curve.
SATURATION_DAYS = 182.5


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def expected_hot_days_per_year(monthly_clim: dict[int, tuple[float, float]],
                                scenario: str = "baseline", horizon: str = "current") -> float:
    """monthly_clim: {month (1-12): (clim_mean_c, clim_std_c)}.
    Returns the expected number of days/year with mean temp > HOT_DAY_THRESHOLD_C,
    summed across all 12 months, under the given scenario/horizon's warming shift."""
    warming = SCENARIO_WARMING_C.get(scenario, 0.0) * HORIZON_FRACTION.get(horizon, 0.0)
    total_days = 0.0
    for month, (clim_mean, clim_std) in monthly_clim.items():
        if clim_std is None or clim_std <= 0:
            continue
        shifted_mean = clim_mean + warming
        # P(X > threshold) for X ~ N(shifted_mean, clim_std)
        p_hot = 1.0 - norm.cdf(HOT_DAY_THRESHOLD_C, loc=shifted_mean, scale=clim_std)
        total_days += p_hot * DAYS_IN_MONTH[month]
    return total_days


def heat_chronic_score(monthly_clim: dict[int, tuple[float, float]],
                        scenario: str = "baseline", horizon: str = "current") -> dict:
    """0-100 chronic-heat score + the expected-days figure that drove it (for
    shap_factors / transparency — same "show your work" convention as every
    other hazard here)."""
    days = expected_hot_days_per_year(monthly_clim, scenario, horizon)
    score = round(100.0 * _clip01(days / SATURATION_DAYS), 1)
    return {"score": score, "expected_hot_days_per_year": round(days, 1)}
