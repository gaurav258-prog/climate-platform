"""The multi-year regression fit behind the 'ranged' tier.

A ranged crop earns its euro from a coefficient fitted across MANY years with an honest r² and
a residual band — not a single-event match (circular). These are pure-function tests.
"""
from __future__ import annotations

import math

from ml.features.crop_fit import fit_climate_on_score


# Scattered, NON-periodic scores — a periodic score sequence would alias with the
# alternate-bearing cycle that decompose() removes, and part of the injected signal would be
# eaten as "cycle". Real crop years are not periodic in their drought, so this is the honest case.
_SCATTERED = [41, 12, 68, 25, 55, 8, 73, 33, 60, 19, 48, 84, 15, 52, 29,
              66, 38, 5, 71, 44, 22, 58, 80, 10, 63]


def _synthetic(slope, intercept, noise, n=25):
    """Build a production series whose cycle-decomposed climate anomaly is, by construction,
    intercept + slope*score + noise. Pure-growth trend, no injected cycle, so decompose()
    recovers most of the injected climate (its centred MA legitimately attenuates a little)."""
    prod, score_by_year = {}, {}
    for i, sc in enumerate(_SCATTERED[:n]):
        year = 1990 + i
        # deterministic pseudo-noise, no RNG (Math.random is unavailable; tests must be stable)
        e = noise * math.sin(i * 1.7)
        climate = intercept + slope * sc + e
        prod[year] = 1000.0 * (1.02 ** i) * (1 + climate / 100.0)
        score_by_year[year] = sc
    return prod, score_by_year


def test_recovers_a_known_slope():
    """A clean linear relationship must come back with the right sign and a strong r²
    (decompose's cycle-removal attenuates the slope a little — that is honest, not a bug)."""
    prod, scores = _synthetic(slope=-0.5, intercept=10.0, noise=1.0)
    fit = fit_climate_on_score(prod, scores, "drought")
    assert fit is not None
    assert fit.slope < 0                       # a hazard hurts yield
    assert fit.r2 > 0.55                        # low noise → strong fit (some cycle attenuation)
    assert fit.n_years >= 12


def test_too_few_years_refuses():
    """A fit on a handful of points is exactly the over-fitting this tier exists to avoid."""
    prod, scores = _synthetic(slope=-0.5, intercept=10.0, noise=1.0, n=8)
    assert fit_climate_on_score(prod, scores, "drought") is None


def test_prediction_band_widens_away_from_training_mean():
    """The interval must be honest: wider for a score far outside the years we trained on."""
    prod, scores = _synthetic(slope=-0.4, intercept=8.0, noise=6.0)
    fit = fit_climate_on_score(prod, scores, "drought")
    lo_mid, mid_mid, hi_mid = fit.predict(fit.score_mean)     # at the mean
    lo_far, mid_far, hi_far = fit.predict(fit.score_mean + 40)  # far out
    assert (hi_far - lo_far) > (hi_mid - lo_mid)


def test_band_scales_with_z():
    prod, scores = _synthetic(slope=-0.4, intercept=8.0, noise=6.0)
    fit = fit_climate_on_score(prod, scores, "drought")
    lo1, mid1, hi1 = fit.predict(70, z=1.0)
    lo2, mid2, hi2 = fit.predict(70, z=2.0)
    assert mid1 == mid2                                       # same centre
    assert (hi2 - lo2) > (hi1 - lo1)                          # 95% wider than 68%
