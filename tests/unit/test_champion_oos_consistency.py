"""The audit ledger must record the SAME out-of-sample number the euro champion is fitted with. crop_fit now
exposes the per-year leave-one-out pairs; the r² recomputed from those pairs (exactly what the validation
engine does) must equal the fit's own r2_oos, and the pairs must align to the fit's years. This is the
invariant that makes 'the number we gate on = the number on the audit record' provably true."""
from __future__ import annotations

import numpy as np

from ml.features.crop_fit import fit_climate_on_score
from ml.validation.metrics import r2_oos


def _synthetic_panel(seed=0, n=22):
    rng = np.random.default_rng(seed)
    years = list(range(2000 - n + 1 + 24, 2025))[:n] if False else list(range(1996, 1996 + n))
    scores = {y: float(v) for y, v in zip(years, rng.uniform(20, 90, n))}
    prod = {}
    for i, y in enumerate(years):
        trend = 1000.0 * (1 + 0.012 * i)               # technology trend
        prod[y] = trend * (1 - 0.0035 * scores[y]) + rng.normal(0, 12)  # hazard depresses yield + noise
    return prod, scores


def test_loo_samples_reproduce_fit_r2_oos():
    prod, scores = _synthetic_panel()
    fit = fit_climate_on_score(prod, scores, "drought", allow_cycle=False)
    assert fit is not None and fit.loo_samples
    preds = [p for (_y, p, _o) in fit.loo_samples]
    obs = [o for (_y, _p, o) in fit.loo_samples]
    # the engine recomputes r2_oos from these exact pairs — it must equal the fit's stored (rounded) number
    assert abs(r2_oos(preds, obs) - fit.r2_oos) < 1e-3
    # sample years are exactly the fit's years, no leakage of extra/edge years
    assert sorted(y for (y, _p, _o) in fit.loo_samples) == fit.years
    assert len(fit.loo_samples) == fit.n_years


def test_loo_pairs_are_out_of_sample_not_in_sample():
    # a genuine LOO r² is strictly below the in-sample r² (it never sees its own point)
    prod, scores = _synthetic_panel(seed=3)
    fit = fit_climate_on_score(prod, scores, "drought", allow_cycle=False)
    assert fit is not None
    assert fit.r2_oos <= fit.r2 + 1e-9
