"""Validation engine — the metric-by-kind computation + gating (pure, no DB)."""
from services.validation.engine import ValidationResult, _compute


def _res(kind, predicted, observed):
    return ValidationResult(hazard_type="x", kind=kind, predicted=predicted, observed=observed,
                            target_source="test")


def test_regression_passes_and_grades():
    obs = [10, 20, 30, 40, 50, 60]
    metrics, grade, passed, gate = _compute(_res("regression", obs, obs))  # perfect
    assert metrics["r2_oos"] == 1.0 and grade.value == "strong" and passed is True
    assert gate.startswith("regression_r2")


def test_regression_fails_gate_when_uncorrelated():
    obs = [10, 20, 30, 40, 50, 60]
    pred = [60, 10, 55, 15, 50, 20]         # anti-/un-correlated → r² below 0.40
    metrics, grade, passed, gate = _compute(_res("regression", pred, obs))
    assert passed is False and grade.value in ("weak", "insufficient")


def test_discrimination_monotone_bands_pass():
    # scores across all four fixed bands; observed counts rise with the band → PASS
    pred = [10, 12, 30, 35, 60, 65, 90, 95]
    obs = [0, 0, 1, 1, 2, 2, 5, 6]
    metrics, grade, passed, gate = _compute(_res("discrimination", pred, obs))
    assert metrics["spearman"] is not None and metrics["monotonic"] is True
    assert passed is True and gate.startswith("discrimination")


def test_discrimination_no_skill_fails():
    pred = [10, 90, 12, 88, 30, 60, 33, 62]
    obs = [3, 0, 4, 1, 0, 5, 2, 0]          # observed unrelated to score
    metrics, grade, passed, gate = _compute(_res("discrimination", pred, obs))
    assert passed is False
