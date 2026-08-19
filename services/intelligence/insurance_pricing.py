"""
Insurance pricing — a SECOND sector built entirely on canonical_scores.

This module exists to prove "consistency by design". The bank vertical reads
canonical_scores by H3 cell and applies TCFD materiality logic. Insurance reads
THE SAME canonical_scores by H3 cell and applies actuarial logic (expected loss,
technical premium). It adds only sector-specific math:

  * it imports the SAME projection primitive the bank uses
    (asset_risk_projection.project) — an insured location is just a located
    asset, so projection is shared, not reinvented;
  * it imports the SAME canonical vocabulary (score buckets, scenarios);
  * it changes NOTHING in canonical_scores, the data model, or the vocabulary.

That additivity is the whole point: a new sector is a pure layer over the golden
source, not a new copy of it. The honesty rule carries over too — a location
with no canonical score is never given a fabricated premium.

The loss curve here is a documented placeholder. Real calibration comes from the
platform's OutcomeFeedback table (realized events vs. predicted scores).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from core.types import score_to_bucket
from services.intelligence.asset_risk_projection import (
    Asset,
    CanonicalScoreRow,
    project,
)


@dataclass(frozen=True)
class InsuredLocation:
    """A covered location. IS-A located asset (asset_id, h3_cell) + sum insured."""
    location_id: str
    h3_cell: Optional[str]
    sum_insured: float
    currency: str = "EUR"


@dataclass(frozen=True)
class PricingParams:
    """
    Actuarial parameters. Defaults are illustrative placeholders, not a filed
    rate. `min_annual_prob`/`max_annual_prob` anchor the loss curve at score 0
    and 100; `mean_damage_ratio` is the average share of sum-insured lost given
    an event; loadings build the technical premium off the pure premium (EAL).
    """
    min_annual_prob: float = 0.001     # score 0   → ~1-in-1000 / year
    max_annual_prob: float = 0.20      # score 100 → ~1-in-5 / year
    mean_damage_ratio: float = 0.30    # avg fraction of sum insured lost per event
    expense_ratio: float = 0.25        # acquisition + admin
    profit_load: float = 0.10          # capital cost / margin


@dataclass(frozen=True)
class PolicyPricing:
    location_id: str
    h3_cell: Optional[str]
    hazard_type: Optional[str]
    scenario: str
    time_horizon: str
    risk_score: Optional[float]
    risk_bucket: Optional[str]
    annual_loss_probability: Optional[float]
    expected_annual_loss: Optional[float]   # pure premium, in policy currency
    technical_premium: Optional[float]      # EAL × (1 + loadings)
    currency: str
    source: str                             # 'canonical' | 'no_canonical_score' | ...
    loss_curve_source: str = "placeholder"  # 'placeholder' | 'isotonic_outcome_feedback'


class LossCurve:
    """
    Maps a 0–100 canonical score to an annual loss-event probability. Two
    implementations: the parametric placeholder, and a CalibratedLossCurve fitted
    from OutcomeFeedback (services/intelligence/loss_curve_calibration.py).
    Pricing depends on this interface, not on a fixed curve.
    """
    calibrated: bool = False
    provenance: dict = {}

    def annual_loss_probability(self, score: float) -> float:  # pragma: no cover
        raise NotImplementedError


class PlaceholderLossCurve(LossCurve):
    """The documented geometric placeholder — used until calibration data exists."""
    calibrated = False

    def __init__(self, params: "PricingParams" = None, reason: str = "no calibration applied"):
        self.params = params or PricingParams()
        self.provenance = {"method": "placeholder_geometric", "reason": reason}

    def annual_loss_probability(self, score: float) -> float:
        return annual_loss_probability(score, self.params)


# ── Pure actuarial functions (the only sector-specific logic) ────────────────

def annual_loss_probability(score: float, params: PricingParams = PricingParams()) -> float:
    """
    Map a 0–100 canonical risk score to an annual loss-event probability.
    Geometric interpolation between min and max anchors — monotonic increasing,
    smooth. Placeholder calibration; replace with OutcomeFeedback-fitted curve.
    """
    if score < 0 or score > 100:
        raise ValueError(f"score out of range [0,100]: {score}")
    lo, hi = params.min_annual_prob, params.max_annual_prob
    return lo * (hi / lo) ** (score / 100.0)


def expected_annual_loss(sum_insured: float, score: float,
                         params: PricingParams = PricingParams(),
                         loss_curve: "LossCurve" = None) -> float:
    """
    EAL (pure premium) = sum insured × annual loss probability × damage ratio.
    Uses `loss_curve` if given (e.g. a CalibratedLossCurve), else the placeholder.
    """
    curve = loss_curve or PlaceholderLossCurve(params)
    return sum_insured * curve.annual_loss_probability(score) * params.mean_damage_ratio


def technical_premium(eal: float, params: PricingParams = PricingParams()) -> float:
    """Technical premium = pure premium loaded for expenses and capital cost."""
    return eal * (1.0 + params.expense_ratio + params.profit_load)


# ── Portfolio pricing — reuses the SAME projection the bank vertical uses ─────

def price_portfolio(
    locations: Iterable[InsuredLocation],
    scores: Iterable[CanonicalScoreRow],
    *,
    scenario: str = "baseline",
    time_horizon: str = "current",
    params: PricingParams = PricingParams(),
    loss_curve: "LossCurve" = None,
) -> list[PolicyPricing]:
    """
    Price each insured location off canonical_scores. The risk lookup is the
    SHARED projection (asset_risk_projection.project) — identical to how the
    bank vertical derives an asset's physical risk. Only the math on top differs.

    `loss_curve` selects the score→probability mapping: pass a CalibratedLossCurve
    (fitted from OutcomeFeedback) to price on realized outcomes, or leave None to
    use the documented placeholder. Each PolicyPricing records which was used.

    Locations whose cell has no canonical score are returned priced=None with the
    projection's reason — never given a made-up premium.
    """
    locations = list(locations)
    by_id = {loc.location_id: loc for loc in locations}
    curve = loss_curve or PlaceholderLossCurve(params)
    curve_source = "isotonic_outcome_feedback" if curve.calibrated else "placeholder"

    # Same substrate as banking: project canonical scores onto located assets.
    risks = project(
        (Asset(asset_id=loc.location_id, h3_cell=loc.h3_cell) for loc in locations),
        scores,
        scenario=scenario,
        time_horizon=time_horizon,
    )

    out: list[PolicyPricing] = []
    for r in risks:
        loc = by_id[r.asset_id]
        if r.source != "canonical" or r.risk_score is None:
            out.append(PolicyPricing(
                location_id=loc.location_id, h3_cell=r.h3_cell, hazard_type=r.hazard_type,
                scenario=r.scenario, time_horizon=r.time_horizon,
                risk_score=None, risk_bucket=None, annual_loss_probability=None,
                expected_annual_loss=None, technical_premium=None,
                currency=loc.currency, source=r.source, loss_curve_source=curve_source,
            ))
            continue
        eal = expected_annual_loss(loc.sum_insured, r.risk_score, params, loss_curve=curve)
        out.append(PolicyPricing(
            location_id=loc.location_id, h3_cell=r.h3_cell, hazard_type=r.hazard_type,
            scenario=r.scenario, time_horizon=r.time_horizon,
            risk_score=r.risk_score,
            risk_bucket=r.risk_bucket or score_to_bucket(r.risk_score).value,
            annual_loss_probability=curve.annual_loss_probability(r.risk_score),
            expected_annual_loss=eal,
            technical_premium=technical_premium(eal, params),
            currency=loc.currency,
            source="canonical",
            loss_curve_source=curve_source,
        ))
    return out


def portfolio_summary(pricings: Iterable[PolicyPricing]) -> dict:
    """Roll up a priced book: total sum at risk, EAL, premium, coverage gaps."""
    priced = [p for p in pricings if p.source == "canonical"]
    unpriced = [p for p in pricings if p.source != "canonical"]
    return {
        "policies_priced": len(priced),
        "policies_unpriced": len(unpriced),
        "total_expected_annual_loss": round(sum(p.expected_annual_loss for p in priced), 2),
        "total_technical_premium": round(sum(p.technical_premium for p in priced), 2),
        "unpriced_reasons": sorted({p.source for p in unpriced}),
    }
