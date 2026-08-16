"""Separate a crop's ALTERNATE-BEARING cycle from its climate signal.

WHY THIS EXISTS. Several of our crops alternate-bear: a heavy crop drains the tree's
reserves, so the next year is light — a ~2-year oscillation with no weather in it at all.
Spanish olives swing 2012 -53%, 2013 +154%, 2014 -53%. Brazilian arabica runs off-years of
-13.2/-12.6/-12.8/-7.1/-2.4/-5.6/-11.2/-15.2% across 2005-2019, all weather-free.

Hand a raw -19% or -52% year to a drought coefficient and you attribute the tree's own
biology to climate. That is exactly how coffee's calibration came to be ~2.3x over-attributed
(see migration coffee_demote_20260716). This module is the fix, and it is a precondition for
backtesting olives, almonds, wine and coffee — every alternate-bearing crop we hold.

METHOD (deliberately simple, so it is auditable):
  1. Work in LOG production, so shocks are multiplicative and comparable across origins.
  2. Remove the long-run trend (area expansion, yield improvement) with a centered rolling
     MEDIAN — robust to both the cycle and to outlier years, unlike a mean.
  3. Fit d_t = phi * d_(t-1) on the detrended deviations. phi < 0 IS alternate bearing: last
     year's surplus predicts this year's deficit. phi is estimated on the WHOLE history, so a
     single event cannot set it.
  4. For a target year, the cycle EXPECTS phi * d_(t-1). Whatever is left over — the residual
     — is the climate-attributable anomaly. That residual, not the raw YoY, is what a hazard
     coefficient may be calibrated against.

HONEST LIMITS, stated because they bound what this can claim:
  * The residual is "not explained by trend or cycle". It is not proof of climate: pests,
    war, policy and price-driven abandonment also land there. It is an UPPER BOUND on the
    climate share, which is why we still require a hazard that independently corroborates it.
  * phi needs history. Under ~12 usable years we do not claim a cycle at all.
  * A crop with phi ~ 0 (cocoa: +13.0/+9.7/-9.0/+24.5/+3.9/+5.8/-1.6/+1.3/+5.9/-22.7/+3.7)
    has no cycle to remove, and its raw anomaly already IS the climate signal.
"""
from __future__ import annotations

import math
from typing import Optional

# Below this many usable years we refuse to characterise a cycle.
MIN_YEARS = 12
# |phi| at or above this is a real alternate-bearing signal rather than noise.
PHI_ALTERNATE_BEARING = 0.20

# Alternate bearing is a BIOLOGY of perennial fruit/nut trees & vines (a heavy crop drains the
# tree, the next is light). ANNUAL crops (cereals, oilseeds, pulses, cane) cannot alternate-bear:
# any measured phi on them is spurious autocorrelation, and removing it as a "cycle" strips real
# climate variance (found 2026-08-16: it suppressed Brazil soy's drought signal, r²_oos 0.12→0.37).
# So de-cycling is applied ONLY to crops on this list; everything else is simple-detrended (phi=0).
ALTERNATE_BEARING_CROPS = (
    "olive", "almond", "pistachio", "apple", "pear", "avocado", "mango", "cherry", "apricot",
    "plum", "walnut", "pecan", "citrus", "orange", "mandarin", "lemon", "lime", "grape", "wine",
    "coffee", "arabica", "cocoa",   # perennial tree crops; cocoa phi≈0 so this is neutral for it
)


def is_alternate_bearing(commodity: str) -> bool:
    """Whether a crop can biologically alternate-bear (→ its cycle should be decomposed out).
    Annual crops (wheat, maize, soy, barley, sunflower, sorghum, cane…) return False → detrend only."""
    c = (commodity or "").lower()
    return any(k in c for k in ALTERNATE_BEARING_CROPS)
# Half-width of the centered trend window. The FULL window is 2*K+1 points with half weights
# at the ends — the classical "2xk" moving average, which cancels a period-2 cycle EXACTLY.
# K=3 (a 7-year span) keeps recent target years like 2022 inside a full symmetric window while
# diluting any single collapse year to ~1/6 leverage on the trend.
TREND_K = 3


def _centered_trend(values: list[float], k: int = TREND_K):
    """Centered 2xk moving average in log space -> (trend, full_window_flag).

    WHY NOT A ROLLING MEDIAN (the first version of this, and it was wrong): the median of an
    alternating series FOLLOWS the alternation — with 5 'on' and 4 'off' years in the window
    the median IS the on-value — so the trend silently absorbed the very cycle we are trying
    to measure. phi collapsed toward 0 and the climate share came out overstated.

    An even-width centered average weights one 'on' against one 'off' and the period-2 cycle
    cancels arithmetically. The cost is outlier sensitivity (a mean, not a median), bounded
    here to ~1/6 by the window width — and a collapse pulling the trend DOWN only makes the
    measured shock SMALLER, i.e. the bias is conservative.

    Years without a full symmetric window are flagged: their trend is extrapolated from the
    nearest full-window year, and they must not be used to calibrate."""
    n = len(values)
    trend: list[float] = [0.0] * n
    full: list[bool] = [False] * n
    for i in range(n):
        if i - k < 0 or i + k >= n:
            continue
        w = values[i - k:i + k + 1]
        # half weights at the two ends => even effective width => period-2 cancels
        s = 0.5 * w[0] + sum(w[1:-1]) + 0.5 * w[-1]
        trend[i] = s / (2 * k)
        full[i] = True

    idx = [i for i in range(n) if full[i]]
    if not idx:
        return None, full
    # Edge years: carry the slope of the nearest full-window pair outward rather than letting
    # a truncated (asymmetric) window invent a signal — a truncated window on a growing series
    # produced a spurious -9.3% "climate" anomaly in year one.
    first, last = idx[0], idx[-1]
    slope_lo = (trend[idx[1]] - trend[first]) if len(idx) > 1 else 0.0
    slope_hi = (trend[last] - trend[idx[-2]]) if len(idx) > 1 else 0.0
    for i in range(first - 1, -1, -1):
        trend[i] = trend[i + 1] - slope_lo
    for i in range(last + 1, n):
        trend[i] = trend[i - 1] + slope_hi
    return trend, full


def decompose(series: dict, target_year: Optional[int] = None, allow_cycle: bool = True) -> dict:
    """series: {year: production_tonnes} (gaps allowed; non-positive values dropped).

    Returns {phi, alternate_bearing, n_years, years: {year: {...}}, target: {...}} where each
    year carries:
      log_dev        — detrended log deviation (the crop's own trend removed)
      cycle_expected — what the alternate-bearing cycle predicts for this year
      climate_resid  — what the cycle does NOT explain (log units)
      climate_pct    — that residual as a % production anomaly  <-- calibrate against THIS
      raw_yoy_pct    — the naive year-on-year, for comparison
    """
    pts = sorted((int(y), float(v)) for y, v in series.items() if v and float(v) > 0)
    if len(pts) < MIN_YEARS:
        return {"phi": None, "alternate_bearing": False, "n_years": len(pts), "years": {},
                "note": f"only {len(pts)} usable years; need >= {MIN_YEARS} to characterise a cycle"}

    years = [y for y, _ in pts]
    logy = [math.log(v) for _, v in pts]
    trend, full = _centered_trend(logy)
    if trend is None:
        return {"phi": None, "alternate_bearing": False, "n_years": len(pts), "years": {},
                "note": f"series too short for a symmetric {2 * TREND_K + 1}-year trend window"}
    dev = [a - b for a, b in zip(logy, trend)]

    # phi from OLS through the origin on (d_(t-1), d_t) — only consecutive years count, so a
    # gap in the series cannot manufacture a cycle.
    num = den = 0.0
    for i in range(1, len(years)):
        if years[i] - years[i - 1] != 1:
            continue
        # only full-window years: an extrapolated edge trend would bias phi
        if not (full[i] and full[i - 1]):
            continue
        num += dev[i - 1] * dev[i]
        den += dev[i - 1] ** 2
    phi = (num / den) if den > 0 else 0.0
    # Annual crops cannot alternate-bear: force phi=0 so climate_pct is the simple detrended
    # deviation (no spurious cycle removed). Only genuine perennials keep their measured cycle.
    if not allow_cycle:
        phi = 0.0
    alternate = phi <= -PHI_ALTERNATE_BEARING

    out = {}
    for i, y in enumerate(years):
        prev_dev = dev[i - 1] if (i > 0 and years[i] - years[i - 1] == 1) else None
        expected = phi * prev_dev if prev_dev is not None else 0.0
        resid = dev[i] - expected
        prev_v = pts[i - 1][1] if (i > 0 and years[i] - years[i - 1] == 1) else None
        out[y] = {
            "production": pts[i][1],
            "log_dev": round(dev[i], 4),
            "cycle_expected": round(expected, 4),
            "climate_resid": round(resid, 4),
            # exp(resid)-1: the % production anomaly the cycle cannot account for
            "climate_pct": round((math.exp(resid) - 1) * 100, 2),
            "raw_yoy_pct": round((pts[i][1] - prev_v) / prev_v * 100, 2) if prev_v else None,
            # False => the trend here was extrapolated from a truncated window. Such a year
            # must NOT be calibrated against: a truncated window invents signal (a pure-growth
            # series produced a spurious -9.3% "climate" anomaly in its first year).
            "trend_full_window": full[i],
        }

    res = {
        "phi": round(phi, 4),
        "alternate_bearing": alternate,
        "n_years": len(pts),
        "span": f"{years[0]}-{years[-1]}",
        "years": out,
    }
    if target_year is not None:
        res["target"] = out.get(target_year)
    return res


def climate_attributable_pct(series: dict, target_year: int) -> Optional[float]:
    """The % production anomaly in `target_year` NOT explained by trend or alternate bearing.
    This is the number a hazard coefficient may be calibrated against — never the raw YoY.

    Returns None when the year cannot carry a calibration: too little history, or the year
    sits at the edge of the series where the trend had to be extrapolated."""
    d = decompose(series, target_year)
    t = d.get("target")
    if not t or not t.get("trend_full_window"):
        return None
    return t["climate_pct"]
