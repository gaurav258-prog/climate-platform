"""The out-of-sample isotonic challenger must be genuinely out-of-sample and independent: it recovers a real
monotone relationship on held-out points, has no skill on noise, and never sees its own point."""
from __future__ import annotations

import numpy as np

from ml.features.challenger import isotonic_loo
from ml.validation.metrics import r2_oos, spearman


def _pts(xs, ys):
    return list(zip([float(x) for x in xs], [float(y) for y in ys]))


def test_isotonic_loo_recovers_monotone_signal_out_of_sample():
    rng = np.random.default_rng(4)
    xs = np.linspace(0, 100, 24)
    ys = -0.4 * xs + rng.normal(0, 3, 24)              # hazard drives loss down (decreasing)
    preds = isotonic_loo(_pts(xs, ys), increasing=False)
    assert preds is not None and len(preds) == 24
    assert r2_oos(preds, ys) > 0.5                     # held-out predictions track the truth
    assert spearman(preds, ys) > 0.5                   # predictions and observations move together


def test_isotonic_loo_no_skill_on_noise():
    rng = np.random.default_rng(8)
    xs = rng.uniform(0, 100, 20)
    ys = rng.normal(0, 5, 20)
    preds = isotonic_loo(_pts(xs, ys), increasing=False)
    assert preds is not None
    assert r2_oos(preds, ys) < 0.4                     # unrelated → no out-of-sample skill


def test_isotonic_loo_too_few_points_returns_none():
    assert isotonic_loo(_pts(range(6), range(6)), increasing=True) is None


def test_isotonic_loo_flat_predictor_returns_none():
    assert isotonic_loo(_pts([5.0] * 15, range(15)), increasing=True) is None


def test_isotonic_loo_predictions_exclude_own_point():
    # perfect monotone step; a genuine LOO cannot perfectly reproduce an isolated extreme it didn't see
    xs = list(range(15))
    ys = list(range(15))
    preds = isotonic_loo(_pts(xs, ys), increasing=True)
    assert preds is not None
    # the largest x was held out, so its prediction is pulled below the true max (clipped to seen range)
    assert preds[-1] < ys[-1]
