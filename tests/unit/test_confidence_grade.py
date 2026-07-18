"""The Confidence Grade — transparent A–E summary of trust in a crop's euro.

Locks the worked examples the spec was designed around, and the honesty rules: the cap (weak
predictive power can't exceed C) and the fact that missing evidence scores Weak, never passes.
"""
from __future__ import annotations

from ml.confidence_grade import grade


def test_olive_is_B():
    """Olive (ranged): OOS r²=0.44 (fair), 31 yrs (strong), band 74% vs 68% (strong),
    ranged (fair) → 1+2+2+1 = 6 → B."""
    g = grade(tier="ranged", r2_oos=0.44, n_years=31, band_cov68=0.74)
    assert g.grade == "B" and g.total == 6 and not g.capped


def test_wheat_is_C_and_capped():
    """Wheat (ranged): OOS r²=0.24 (weak), 20 yrs (fair), band 65% (strong), ranged (fair)
    → 0+1+2+1 = 4 → would be C anyway, but weak predictive also CAPS it at C."""
    g = grade(tier="ranged", r2_oos=0.24, n_years=20, band_cov68=0.65)
    assert g.grade == "C"
    assert g.checks[0]["label"] == "weak"


def test_cocoa_is_B():
    """Cocoa (backtested): reproduced within 3% (strong), 1 event (fair), single-event caveat
    (fair), real event (strong) → 2+1+1+2 = 6 → B. A single event holds it below A."""
    g = grade(tier="backtested", reproduction_err_pct=3.0, n_events=1)
    assert g.grade == "B" and g.total == 6


def test_honesty_cap_blocks_A_when_predictive_weak():
    """Even with deep history and a perfectly calibrated band, weak out-of-sample power caps at C."""
    g = grade(tier="ranged", r2_oos=0.20, n_years=40, band_cov68=0.68)
    assert g.grade == "C" and g.capped is True


def test_a_grade_is_achievable_but_earned():
    """A strong rain-fed crop — high OOS r², deep history, calibrated band — reaches A."""
    g = grade(tier="ranged", r2_oos=0.65, n_years=34, band_cov68=0.70)
    assert g.grade == "A" and g.total >= 7


def test_missing_out_of_sample_scores_weak_not_pass():
    """A fit with no measured OOS r² must not sail through — unknown is Weak, and caps the grade."""
    g = grade(tier="ranged", r2_oos=None, n_years=30, band_cov68=0.68)
    assert g.checks[0]["label"] == "weak"
    assert g.grade == "C"       # capped


def test_backtested_needs_a_reproduction_figure():
    """A 'backtested' claim with no reproduction error can't score strong on predictive power."""
    g = grade(tier="backtested", reproduction_err_pct=None, n_events=1)
    assert g.checks[0]["label"] == "weak"
