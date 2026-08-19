"""
Tests for loss-curve calibration from OutcomeFeedback.

Covers: a credible dataset yields a monotonic calibrated curve that pricing
uses; thin/degenerate data falls back to the placeholder with a recorded reason;
annualization from the prediction window is explicit and correct.
"""


from datetime import datetime, timezone

import pytest

from services.intelligence.asset_risk_projection import CanonicalScoreRow
from services.intelligence.insurance_pricing import (
    InsuredLocation,
    PlaceholderLossCurve,
    price_portfolio,
)
from services.intelligence.loss_curve_calibration import (
    CalibratedLossCurve,
    Observation,
    fit_loss_curve,
)


def _synthetic(n_per_score=40, window_days=365):
    """Build a dataset where event frequency rises with score (true signal)."""
    obs = []
    for score in range(0, 101, 10):
        true_p = 0.02 + 0.006 * score          # 2% at 0 → 62% at 100, monotonic
        n_events = round(true_p * n_per_score)
        for i in range(n_per_score):
            obs.append(Observation(float(score), i < n_events, lead_days=window_days))
    return obs


# ── Fit on credible data ─────────────────────────────────────────────────────

def test_fit_produces_calibrated_curve():
    curve = fit_loss_curve(_synthetic(), min_samples=100, min_events=10)
    assert isinstance(curve, CalibratedLossCurve)
    assert curve.calibrated is True
    assert curve.provenance["method"] == "isotonic_outcome_feedback"
    assert curve.provenance["n_samples"] == 11 * 40


def test_calibrated_curve_is_monotonic():
    curve = fit_loss_curve(_synthetic(), min_samples=100, min_events=10)
    probs = [curve.window_event_probability(s) for s in range(0, 101, 5)]
    assert probs == sorted(probs)                     # non-decreasing in score


def test_calibrated_probability_tracks_empirical_rate():
    # At score 50 the synthetic true window-rate is 0.02 + 0.006*50 = 0.32
    curve = fit_loss_curve(_synthetic(n_per_score=200), min_samples=100, min_events=10)
    assert curve.window_event_probability(50) == pytest.approx(0.32, abs=0.05)


# ── Annualization is explicit ────────────────────────────────────────────────

def test_short_window_annualizes_upward():
    # 7-day window with a 10% per-window rate annualizes to ~1-(0.9)^(365/7)
    [Observation(80.0, i < 10, lead_days=7) for i in range(100)] + \
          [Observation(80.0, False, lead_days=7) for _ in range(0)]
    curve = fit_loss_curve(
        [Observation(float(s), (s >= 80 and i < 10), lead_days=7)
         for s in (0, 80) for i in range(100)],
        min_samples=50, min_events=5,
    )
    p_window = curve.window_event_probability(80)
    annual = curve.annual_loss_probability(80)
    assert annual > p_window                          # annual exceeds per-window
    expected = 1 - (1 - p_window) ** (365.25 / 7)
    assert annual == pytest.approx(min(0.95, expected), abs=1e-6)


def test_annual_probability_capped():
    curve = fit_loss_curve(
        [Observation(float(s), (s >= 50 and i < 30), lead_days=1)
         for s in (0, 50) for i in range(100)],
        min_samples=50, min_events=5,
    )
    assert curve.annual_loss_probability(50) <= 0.95


# ── Graceful fallback (honesty rule) ─────────────────────────────────────────

def test_fallback_on_too_few_samples():
    curve = fit_loss_curve([Observation(50.0, True)], min_samples=200)
    assert isinstance(curve, PlaceholderLossCurve)
    assert curve.calibrated is False
    assert "insufficient samples" in curve.provenance["reason"]


def test_fallback_on_too_few_events():
    obs = [Observation(float(s % 100), False) for s in range(300)]
    curve = fit_loss_curve(obs, min_samples=100, min_events=10)
    assert curve.calibrated is False
    assert "too few events" in curve.provenance["reason"]


def test_fallback_on_no_score_variance():
    obs = [Observation(50.0, i < 60) for i in range(300)]
    curve = fit_loss_curve(obs, min_samples=100, min_events=10)
    assert curve.calibrated is False
    assert "no score variance" in curve.provenance["reason"]


# ── Calibrated curve flows into pricing ──────────────────────────────────────

def test_pricing_uses_calibrated_curve_and_records_provenance():
    curve = fit_loss_curve(_synthetic(n_per_score=100), min_samples=100, min_events=10)
    locs = [InsuredLocation("L1", "c", sum_insured=1_000_000)]
    scores = [CanonicalScoreRow("c", "flood", "baseline", "current", 90.0,
                                datetime(2026, 6, 20, tzinfo=timezone.utc), "v1")]

    placeholder_priced = price_portfolio(locs, scores)[0]
    calibrated_priced = price_portfolio(locs, scores, loss_curve=curve)[0]

    assert placeholder_priced.loss_curve_source == "placeholder"
    assert calibrated_priced.loss_curve_source == "isotonic_outcome_feedback"
    # The two curves disagree on the premium → calibration actually changed pricing.
    assert calibrated_priced.technical_premium != placeholder_priced.technical_premium
