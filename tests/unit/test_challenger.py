"""The independent challenger + its corroboration wiring into the confidence grade.

Pins that it's a genuine second opinion (independent of the champion's coefficients), that it agrees
on a linear panel and DIVERGES on a non-linear one, and that corroboration is surfaced-not-additive
while a divergence caps the grade.
"""
import numpy as np

from ml.confidence_grade import grade
from ml.features.challenger import isotonic_challenger


def test_agree_on_linear_panel():
    pts = [(float(s), -0.4 * s) for s in range(10, 90, 4)]  # perfectly linear
    v = isotonic_challenger(pts, -0.4, 0.0, champion_rmse=2.0)
    assert v["verdict"] == "agree" and v["n_years"] >= 12


def test_diverge_on_nonlinear_panel():
    # a threshold/step the linear champion cannot capture — the challenger should flag it
    pts = [(float(s), (0.0 if s < 50 else -40.0)) for s in range(10, 90, 3)]
    xs = np.array([p[0] for p in pts]); ys = np.array([p[1] for p in pts])
    slope = float(((xs - xs.mean()) * (ys - ys.mean())).sum() / ((xs - xs.mean()) ** 2).sum())
    intc = float(ys.mean() - slope * xs.mean())
    v = isotonic_challenger(pts, slope, intc, champion_rmse=1.0)
    assert v["verdict"] == "diverge"


def test_insufficient_on_small_panel():
    v = isotonic_challenger([(10.0, -4.0), (50.0, -20.0)], -0.4, 0.0, 2.0)
    assert v["verdict"] == "insufficient"


def test_challenger_is_independent_of_champion_coefficients():
    pts = [(float(s), -0.4 * s) for s in range(10, 90, 4)]
    a = isotonic_challenger(pts, -0.4, 0.0, 2.0)["challenger_at_ref_pct"]
    b = isotonic_challenger(pts, -0.9, 5.0, 2.0)["challenger_at_ref_pct"]  # different champion
    assert a == b  # the challenger's own estimate does NOT depend on the champion's slope/intercept


def test_corroboration_is_surfaced_not_additive():
    base = grade(tier="ranged", r2_oos=0.6, n_years=30, band_cov68=0.68)
    corr = grade(tier="ranged", r2_oos=0.6, n_years=30, band_cov68=0.68, corroboration="agree")
    assert corr.total == base.total          # agreement never inflates the earned /8
    assert corr.grade == base.grade
    assert any(c["key"] == "corroboration" and c["label"] == "strong" for c in corr.checks)


def test_divergence_caps_grade_at_C():
    strong = grade(tier="ranged", r2_oos=0.7, n_years=30, band_cov68=0.68)
    assert strong.grade in ("A", "B")
    capped = grade(tier="ranged", r2_oos=0.7, n_years=30, band_cov68=0.68, corroboration="diverge")
    assert capped.grade == "C" and capped.capped


def test_no_corroboration_is_backward_compatible():
    g = grade(tier="ranged", r2_oos=0.6, n_years=30, band_cov68=0.68)
    assert all(c["key"] != "corroboration" for c in g.checks)
