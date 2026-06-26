"""
Unit tests for the 3-model EnsembleScorer.

Tests run without DB — pure in-memory training on synthetic data.
"""
import numpy as np
import pandas as pd
import pytest

from ml.scoring.ensemble import EnsembleResult, EnsembleScorer


@pytest.fixture()
def trained_scorer() -> EnsembleScorer:
    """Scorer fitted on a tiny synthetic flood dataset."""
    rng = np.random.default_rng(42)
    n = 200
    X = rng.random((n, 3))
    # Label: positive if first two features sum > 1.2
    y = ((X[:, 0] + X[:, 1]) > 1.2).astype(int)
    scorer = EnsembleScorer(scale_pos_weight=3.0)
    scorer.fit(X, y, feature_cols=["precip_7d", "soil_sat", "runoff"])
    return scorer


def test_fit_populates_pipelines(trained_scorer):
    assert len(trained_scorer._pipelines) >= 2  # at least logistic + xgb
    assert "logistic" in trained_scorer._pipelines


def test_all_three_models_train():
    """With both xgboost and lightgbm installed, all 3 models must train."""
    rng = np.random.default_rng(0)
    X = rng.random((100, 2))
    y = (X[:, 0] > 0.5).astype(int)
    scorer = EnsembleScorer()
    scorer.fit(X, y, feature_cols=["a", "b"])
    assert "xgb" in scorer._pipelines
    assert "lgbm" in scorer._pipelines
    assert "logistic" in scorer._pipelines


def test_score_array_returns_one_result_per_row(trained_scorer):
    X = np.random.default_rng(1).random((50, 3))
    results = trained_scorer.score_array(X)
    assert len(results) == 50


def test_score_range_0_to_100(trained_scorer):
    X = np.random.default_rng(2).random((30, 3))
    for r in trained_scorer.score_array(X):
        assert 0.0 <= r.score <= 100.0
        assert 0.0 <= r.ci_lower <= r.score
        assert r.score <= r.ci_upper <= 100.0


def test_ci_lower_le_score_le_ci_upper(trained_scorer):
    X = np.random.default_rng(3).random((20, 3))
    for r in trained_scorer.score_array(X):
        assert r.ci_lower <= r.score
        assert r.score <= r.ci_upper


def test_per_model_keys(trained_scorer):
    X = np.random.default_rng(4).random((5, 3))
    results = trained_scorer.score_array(X)
    expected_keys = set(trained_scorer._pipelines.keys())
    for r in results:
        assert set(r.per_model.keys()) == expected_keys


def test_high_disagreement_flag(trained_scorer):
    """Disagreement flag must be bool."""
    X = np.random.default_rng(5).random((10, 3))
    for r in trained_scorer.score_array(X):
        assert isinstance(r.high_disagreement, bool)


def test_score_dataframe_adds_columns(trained_scorer):
    df = pd.DataFrame(
        np.random.default_rng(6).random((15, 3)),
        columns=["precip_7d", "soil_sat", "runoff"],
    )
    df["h3_cell"] = "abc"
    out = trained_scorer.score_dataframe(df)
    for col in ["score", "ci_lower", "ci_upper", "ensemble_scores", "high_disagreement"]:
        assert col in out.columns


def test_score_dataframe_ignores_extra_columns(trained_scorer):
    """Extra columns not in feature_cols should be silently ignored."""
    df = pd.DataFrame(
        np.random.default_rng(7).random((5, 3)),
        columns=["precip_7d", "soil_sat", "runoff"],
    )
    df["extra_column"] = 999
    out = trained_scorer.score_dataframe(df)
    assert len(out) == 5


def test_score_before_fit_raises():
    scorer = EnsembleScorer()
    with pytest.raises(RuntimeError, match="fit"):
        scorer.score_array(np.array([[1, 2, 3]]))


def test_n_models_reported_correctly(trained_scorer):
    X = np.random.default_rng(8).random((3, 3))
    results = trained_scorer.score_array(X)
    expected = len(trained_scorer._pipelines)
    for r in results:
        assert r.n_models == expected


def test_deterministic_scores(trained_scorer):
    """Same input must produce identical scores (no randomness at inference)."""
    X = np.random.default_rng(9).random((10, 3))
    r1 = trained_scorer.score_array(X)
    r2 = trained_scorer.score_array(X)
    for a, b in zip(r1, r2):
        assert a.score == b.score
        assert a.ci_lower == b.ci_lower
        assert a.ci_upper == b.ci_upper
