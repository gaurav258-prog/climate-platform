"""Validation metrics — exact known-answer tests. These numbers are the accuracy floor of the whole
backtesting framework, so they are pinned against hand-computable cases."""
import numpy as np
import pytest

from ml.validation import metrics as m


def test_r2_oos_perfect_mean_and_negative():
    obs = np.array([1.0, 2.0, 3.0, 4.0])
    assert m.r2_oos(obs, obs) == pytest.approx(1.0)              # perfect prediction
    assert m.r2_oos(np.full(4, obs.mean()), obs) == pytest.approx(0.0)  # predicting the mean → 0
    worse = m.r2_oos(np.array([4.0, 3.0, 2.0, 1.0]), obs)       # anti-correlated → negative
    assert worse is not None and worse < 0


def test_r2_oos_insufficient():
    assert m.r2_oos([1, 2], [1, 2]) is None                     # < MIN_N
    assert m.r2_oos([1, 2, 3], [5, 5, 5]) is None               # observed has no variance


def test_spearman_monotone():
    a = np.array([1.0, 2, 3, 4, 5])
    assert m.spearman(a, a * 10) == pytest.approx(1.0)          # perfectly rank-correlated
    assert m.spearman(a, -a) == pytest.approx(-1.0)             # perfectly anti-correlated
    assert m.spearman([1, 1, 1], [1, 2, 3]) is None             # no variance in a


def test_auc_separable():
    scores = np.array([0.1, 0.2, 0.8, 0.9])
    pos = np.array([False, False, True, True])
    assert m.auc(scores, pos) == pytest.approx(1.0)             # positives rank above negatives
    assert m.auc(scores, np.array([True, True, False, False])) == pytest.approx(0.0)
    assert m.auc(scores, np.array([False, False, False, False])) is None  # no positives


def test_rmse_mae_bias_brier():
    pred = np.array([2.0, 4.0, 6.0]); obs = np.array([1.0, 4.0, 9.0])
    assert m.rmse(pred, obs) == pytest.approx(np.sqrt((1 + 0 + 9) / 3))
    assert m.mae(pred, obs) == pytest.approx((1 + 0 + 3) / 3)
    assert m.bias(pred, obs) == pytest.approx((1 + 0 - 3) / 3)  # net under-prediction
    assert m.brier([0.0, 1.0], [0.0, 1.0]) == pytest.approx(0.0)   # perfect
    assert m.brier([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)   # worst


def test_grades_and_gates():
    assert m.grade_regression(0.7) == m.Grade.STRONG
    assert m.grade_regression(0.45) == m.Grade.FAIR
    assert m.grade_regression(0.30) == m.Grade.WEAK
    assert m.grade_regression(None) == m.Grade.INSUFFICIENT
    assert m.passes_regression_gate(0.40) is True
    assert m.passes_regression_gate(0.39) is False
    assert m.passes_regression_gate(None) is False

    assert m.grade_discrimination(0.7, True) == m.Grade.STRONG
    assert m.grade_discrimination(0.4, True) == m.Grade.FAIR
    assert m.grade_discrimination(0.1, True) == m.Grade.WEAK
    assert m.passes_discrimination_gate(0.4, True) is True
    assert m.passes_discrimination_gate(0.4, False) is False     # not monotonic → fail


def test_monotonic():
    assert m.monotonic_nondecreasing([1, 2, 2, 3]) is True
    assert m.monotonic_nondecreasing([3, 1]) is False
    assert m.monotonic_nondecreasing([None, 1]) is None


def test_applicability_guard_flags_saturation_not_failure():
    # a wide/frequent hazard where nearly every location has an event → NOT testable, not "failed"
    pred = np.arange(0, 100, 1.0)                      # 100 samples, full score spread
    saturated = np.ones(len(pred))                     # every location has an event (prevalence 100%)
    ok, reason = m.discrimination_applicable(pred, saturated)
    assert ok is False and "saturated" in reason
    # too sparse is also not testable
    sparse = np.zeros(len(pred)); sparse[0] = 1        # 1% prevalence (< 2% floor)
    ok2, _ = m.discrimination_applicable(pred, sparse)
    assert ok2 is False
    # a healthy spread of events IS testable
    healthy = (np.arange(len(pred)) % 2).astype(float)  # 50% prevalence
    ok3, _ = m.discrimination_applicable(pred, healthy)
    assert ok3 is True


def test_continuous_applicable():
    assert m.continuous_applicable([10, 20, 30], [1, 2, 3])[0] is True
    assert m.continuous_applicable([10, 20, 30], [5, 5, 5])[0] is False  # observed no variance
    assert m.continuous_applicable([10, 10, 10], [1, 2, 3])[0] is False  # score no spread
