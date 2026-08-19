"""
Tests for the insurance sector (consistency-by-design proof).

The decisive test is `test_bank_and_insurance_share_one_golden_source`: two
sectors price the SAME canonical_scores rows for the SAME H3 cell, producing
sector-appropriate outputs, with canonical_scores left untouched. If that holds,
adding a sector is additive — the architectural claim is real.
"""

from datetime import datetime, timezone

import pytest

from services.intelligence.asset_risk_projection import Asset, CanonicalScoreRow, project
from services.intelligence.insurance_pricing import (
    InsuredLocation,
    PricingParams,
    annual_loss_probability,
    portfolio_summary,
    price_portfolio,
)


def _dt(day: int) -> datetime:
    return datetime(2026, 6, day, tzinfo=timezone.utc)


def _score(cell, score, hazard="flood", scenario="baseline", horizon="current"):
    return CanonicalScoreRow(cell, hazard, scenario, horizon, score, _dt(20), "v1")


# ── Loss curve ───────────────────────────────────────────────────────────────

def test_loss_probability_anchored_and_bounded():
    p = PricingParams()
    assert annual_loss_probability(0, p) == pytest.approx(p.min_annual_prob)
    assert annual_loss_probability(100, p) == pytest.approx(p.max_annual_prob)
    mid = annual_loss_probability(50, p)
    assert p.min_annual_prob < mid < p.max_annual_prob


def test_loss_probability_monotonic():
    probs = [annual_loss_probability(s) for s in range(0, 101, 10)]
    assert probs == sorted(probs)


def test_loss_probability_rejects_out_of_range():
    with pytest.raises(ValueError):
        annual_loss_probability(120)


# ── Premium behaviour ────────────────────────────────────────────────────────

def test_higher_canonical_score_means_higher_premium():
    locs = [
        InsuredLocation("low", "cell_low", sum_insured=1_000_000),
        InsuredLocation("high", "cell_high", sum_insured=1_000_000),
    ]
    scores = [_score("cell_low", 20), _score("cell_high", 90)]
    priced = {p.location_id: p for p in price_portfolio(locs, scores)}
    assert priced["high"].technical_premium > priced["low"].technical_premium
    assert priced["high"].expected_annual_loss > priced["low"].expected_annual_loss


def test_premium_scales_with_sum_insured():
    locs = [
        InsuredLocation("small", "c", sum_insured=1_000_000),
        InsuredLocation("big", "c", sum_insured=10_000_000),
    ]
    scores = [_score("c", 70)]
    priced = {p.location_id: p for p in price_portfolio(locs, scores)}
    assert priced["big"].technical_premium == pytest.approx(
        priced["small"].technical_premium * 10)


# ── Honesty rule carries over from the bank vertical ─────────────────────────

def test_location_without_score_is_not_priced():
    locs = [InsuredLocation("L1", "unscored_cell", sum_insured=5_000_000)]
    scores = [_score("some_other_cell", 80)]
    [p] = price_portfolio(locs, scores)
    assert p.technical_premium is None          # never a fabricated premium
    assert p.expected_annual_loss is None
    assert p.source == "no_canonical_score"


# ── Shared vocabulary (reconciliation #2) ────────────────────────────────────

def test_scenario_dialect_normalizes_in_pricing():
    locs = [InsuredLocation("L1", "c", sum_insured=1_000_000)]
    scores = [_score("c", 60, scenario="orderly_1_5c", horizon="2030")]
    [p] = price_portfolio(locs, scores, scenario="1.5c", time_horizon="2030")
    assert p.source == "canonical"
    assert p.technical_premium is not None


# ── Portfolio roll-up ────────────────────────────────────────────────────────

def test_portfolio_summary_counts_priced_and_unpriced():
    locs = [
        InsuredLocation("a", "c1", 1_000_000),
        InsuredLocation("b", "c2", 2_000_000),
        InsuredLocation("c", "no_cell", 3_000_000),
    ]
    scores = [_score("c1", 50), _score("c2", 80)]
    summary = portfolio_summary(price_portfolio(locs, scores))
    assert summary["policies_priced"] == 2
    assert summary["policies_unpriced"] == 1
    assert summary["total_technical_premium"] > 0
    assert summary["unpriced_reasons"] == ["no_canonical_score"]


# ── THE PROOF: two sectors, one golden source, unchanged ─────────────────────

def test_bank_and_insurance_share_one_golden_source():
    """
    Bank materiality and insurance pricing consume the SAME canonical_scores
    rows for the SAME cell, each producing its own sector output, and neither
    mutates the source. This is consistency-by-design.
    """
    cell = "cell_shared"
    scores = [_score(cell, 82)]
    scores_snapshot = [(s.h3_cell, s.hazard_type, s.risk_score) for s in scores]

    # Sector 1 — banking: project canonical score onto an asset.
    [bank_risk] = project([Asset(asset_id="bank_asset", h3_cell=cell)], scores)

    # Sector 2 — insurance: price an insured location at the same cell.
    [policy] = price_portfolio(
        [InsuredLocation("policy_at_cell", cell, sum_insured=4_000_000)], scores)

    # Same underlying canonical score reaches both sectors.
    assert bank_risk.risk_score == 82
    assert policy.risk_score == 82
    assert bank_risk.risk_bucket == policy.risk_bucket == "VH"

    # Each derived its own sector-appropriate output from that one score.
    assert hasattr(bank_risk, "source") and bank_risk.source == "canonical"
    assert policy.technical_premium is not None and policy.expected_annual_loss > 0

    # The golden source was not mutated by either consumer.
    assert [(s.h3_cell, s.hazard_type, s.risk_score) for s in scores] == scores_snapshot
