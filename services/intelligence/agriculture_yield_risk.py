"""
Agriculture yield-at-risk — a THIRD sector on canonical_scores.

Banking reads the canonical score and computes TCFD materiality; insurance
computes a premium; agriculture computes yield-at-risk. Same substrate, same
projection, same vocabulary — only the math on top differs.

Two things make agriculture a richer demonstration than insurance:
  * it is genuinely MULTI-HAZARD — drought and heat both drive yield loss, so it
    combines several canonical scores for one parcel (insurance used one);
  * loss depends on the CROP — maize, wheat and soy have different drought/heat
    sensitivities — so the sector carries a small crop model on top of the score.

It still adds nothing to canonical_scores, the vocabulary, or the projection: it
imports them. The honesty rule carries over — a parcel with no canonical score
for the relevant hazards is not given a fabricated loss. Crop sensitivities are
documented placeholders, calibratable later from OutcomeFeedback like the
insurance loss curve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from core.types import normalize_hazard, normalize_scenario, score_to_bucket
from services.intelligence.asset_risk_projection import (
    Asset, CanonicalScoreRow, project,
)

# Hazards that drive crop yield loss (canonical hazard values).
YIELD_HAZARDS = ("drought", "heat_acute")


@dataclass(frozen=True)
class FarmParcel:
    """A located agricultural parcel. IS-A located asset (parcel_id, h3_cell)."""
    parcel_id: str
    h3_cell: Optional[str]
    crop: str
    hectares: float
    expected_yield_t_per_ha: float
    crop_price_per_t: float
    currency: str = "EUR"


@dataclass(frozen=True)
class CropSensitivity:
    """
    Fraction of yield lost at a maximum (score=100) hazard, per hazard. Documented
    placeholders — e.g. maize is more heat-sensitive, wheat more drought-sensitive.
    Calibrate from OutcomeFeedback (realized yield vs predicted score) later.
    """
    drought: float
    heat_acute: float


# Placeholder crop model. Unknown crops fall back to DEFAULT_SENSITIVITY.
CROP_SENSITIVITY: dict[str, CropSensitivity] = {
    "maize":   CropSensitivity(drought=0.55, heat_acute=0.45),
    "wheat":   CropSensitivity(drought=0.50, heat_acute=0.30),
    "soy":     CropSensitivity(drought=0.45, heat_acute=0.40),
    "rice":    CropSensitivity(drought=0.60, heat_acute=0.25),
    "barley":  CropSensitivity(drought=0.45, heat_acute=0.30),
}
DEFAULT_SENSITIVITY = CropSensitivity(drought=0.50, heat_acute=0.35)


@dataclass(frozen=True)
class ParcelYieldRisk:
    parcel_id: str
    h3_cell: Optional[str]
    crop: str
    scenario: str
    time_horizon: str
    hazard_scores: dict = field(default_factory=dict)   # hazard -> score
    yield_loss_fraction: Optional[float] = None
    expected_yield_loss_t: Optional[float] = None
    revenue_at_risk: Optional[float] = None
    currency: str = "EUR"
    source: str = "no_canonical_score"

    @property
    def degraded(self) -> bool:
        """True when this parcel's risk did NOT come from the canonical golden source — a rule-based
        fallback, so its euro is lower-quality and must be flagged, never filed as if canonical (T4b)."""
        return self.source != "canonical"


def _sensitivity(crop: str) -> CropSensitivity:
    return CROP_SENSITIVITY.get(crop.strip().lower(), DEFAULT_SENSITIVITY)


def combined_yield_loss(crop: str, scores_by_hazard: dict) -> float:
    """
    Combine per-hazard losses into one yield-loss fraction. Hazards are treated as
    independent stressors: surviving fraction = ∏(1 − loss_h), so total loss =
    1 − ∏(1 − loss_h). loss_h = crop_sensitivity_h × (score_h / 100).
    """
    sens = _sensitivity(crop)
    surviving = 1.0
    for hazard, score in scores_by_hazard.items():
        s = getattr(sens, hazard, 0.0)
        loss_h = s * (float(score) / 100.0)
        surviving *= (1.0 - loss_h)
    return 1.0 - surviving


def assess_parcels(
    parcels: Iterable[FarmParcel],
    scores: Iterable[CanonicalScoreRow],
    *,
    scenario: str = "baseline",
    time_horizon: str = "current",
) -> list[ParcelYieldRisk]:
    """
    Yield-at-risk per parcel from canonical drought + heat scores. Uses the SHARED
    projection (asset_risk_projection.project) exactly like banking and insurance.
    A parcel with no canonical score for any yield hazard is returned with
    source='no_canonical_score' — never a fabricated loss.
    """
    parcels = list(parcels)
    by_id = {p.parcel_id: p for p in parcels}
    canonical_scenario = normalize_scenario(scenario).value

    risks = project(
        (Asset(asset_id=p.parcel_id, h3_cell=p.h3_cell) for p in parcels),
        scores,
        scenario=scenario,
        time_horizon=time_horizon,
    )

    # Collect the yield-relevant canonical scores per parcel.
    scores_by_parcel: dict[str, dict] = {p.parcel_id: {} for p in parcels}
    for r in risks:
        if r.source == "canonical" and r.hazard_type in YIELD_HAZARDS and r.risk_score is not None:
            scores_by_parcel[r.asset_id][r.hazard_type] = r.risk_score

    out: list[ParcelYieldRisk] = []
    for p in parcels:
        hz = scores_by_parcel[p.parcel_id]
        if not hz:
            out.append(ParcelYieldRisk(
                parcel_id=p.parcel_id, h3_cell=p.h3_cell, crop=p.crop,
                scenario=canonical_scenario, time_horizon=time_horizon,
                currency=p.currency, source="no_canonical_score",
            ))
            continue
        loss_frac = combined_yield_loss(p.crop, hz)
        expected_total_t = p.hectares * p.expected_yield_t_per_ha
        loss_t = expected_total_t * loss_frac
        out.append(ParcelYieldRisk(
            parcel_id=p.parcel_id, h3_cell=p.h3_cell, crop=p.crop,
            scenario=canonical_scenario, time_horizon=time_horizon,
            hazard_scores=hz,
            yield_loss_fraction=loss_frac,
            expected_yield_loss_t=loss_t,
            revenue_at_risk=loss_t * p.crop_price_per_t,
            currency=p.currency,
            source="canonical",
        ))
    return out


def portfolio_summary(risks: Iterable[ParcelYieldRisk]) -> dict:
    """Roll up an agricultural book: parcels assessed, tonnes and revenue at risk."""
    assessed = [r for r in risks if r.source == "canonical"]
    unassessed = [r for r in risks if r.source != "canonical"]
    return {
        "parcels_assessed": len(assessed),
        "parcels_unassessed": len(unassessed),
        "total_yield_loss_t": round(sum(r.expected_yield_loss_t for r in assessed), 2),
        "total_revenue_at_risk": round(sum(r.revenue_at_risk for r in assessed), 2),
        "unassessed_reasons": sorted({r.source for r in unassessed}),
    }
