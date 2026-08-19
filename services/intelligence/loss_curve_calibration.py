"""
Loss-curve calibration — fit the insurance loss probability from realized outcomes.

The insurance sector ships with a documented placeholder loss curve (geometric
interpolation, in insurance_pricing.py). This module replaces it with a curve
FITTED from the platform's OutcomeFeedback table, which records, per past
prediction: the predicted canonical score and whether an event actually occurred
within the prediction window. That is exactly a probability-calibration dataset.

Method: isotonic regression — non-parametric and monotonic, the standard tool
for turning scores into calibrated probabilities. It assumes only that higher
canonical score ⇒ not-lower event probability (which is the platform's whole
premise), and otherwise lets the data speak.

Two honesty guarantees:
  * If there isn't enough signal (too few samples or too few events), it does NOT
    fit a noisy curve — it returns the placeholder, with the reason recorded in
    provenance. Calibration is opt-in on evidence, never forced.
  * `event_occurred` is over the prediction window (prediction_lead_days), so the
    fitted probability is per-window. Converting to an ANNUAL probability is an
    explicit, documented transform — not hidden in the fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
from sklearn.isotonic import IsotonicRegression

from core.types import normalize_hazard
from services.intelligence.insurance_pricing import (
    LossCurve,
    PlaceholderLossCurve,
    PricingParams,
)

ANNUAL_DAYS = 365.25
MAX_ANNUAL_PROB = 0.95           # cap so short-window hazards don't price at ~certainty
DEFAULT_MIN_SAMPLES = 200        # actuarial credibility floor
DEFAULT_MIN_EVENTS = 10          # need enough positives AND negatives to fit


@dataclass(frozen=True)
class Observation:
    """One realized prediction from outcome_feedback."""
    predicted_score: float
    event_occurred: bool
    lead_days: Optional[int] = None


class CalibratedLossCurve(LossCurve):
    """An isotonic score→probability curve fitted from realized outcomes."""
    calibrated = True

    def __init__(self, iso: IsotonicRegression, window_days: float, provenance: dict):
        self._iso = iso
        self.window_days = window_days
        self.provenance = provenance

    def window_event_probability(self, score: float) -> float:
        """P(event within the prediction window | score), from the fit."""
        s = float(min(100.0, max(0.0, score)))
        return float(self._iso.predict([s])[0])

    def annual_loss_probability(self, score: float) -> float:
        """
        Annualize the per-window probability assuming independent windows:
        annual = 1 − (1 − p_window)^(365.25 / window_days), capped.
        """
        p = self.window_event_probability(score)
        factor = ANNUAL_DAYS / self.window_days
        annual = 1.0 - (1.0 - p) ** factor
        return float(min(MAX_ANNUAL_PROB, max(0.0, annual)))


def fit_loss_curve(
    observations: Iterable[Observation],
    *,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_events: int = DEFAULT_MIN_EVENTS,
    params: PricingParams = PricingParams(),
) -> LossCurve:
    """
    Fit an isotonic loss curve, or fall back to the placeholder (flagged with the
    reason) when the data can't support a credible fit. Pure — no DB.
    """
    obs = list(observations)
    n = len(obs)
    scores = np.array([o.predicted_score for o in obs], dtype=float)
    events = np.array([1.0 if o.event_occurred else 0.0 for o in obs], dtype=float)
    n_events = int(events.sum())
    n_neg = n - n_events

    reason = None
    if n < min_samples:
        reason = f"insufficient samples ({n} < {min_samples})"
    elif n_events < min_events:
        reason = f"too few events ({n_events} < {min_events})"
    elif n_neg < min_events:
        reason = f"too few non-events ({n_neg} < {min_events})"
    elif float(scores.max() - scores.min()) == 0.0:
        reason = "no score variance"
    if reason is not None:
        return PlaceholderLossCurve(params, reason=f"fell back: {reason}")

    leads = [float(o.lead_days) for o in obs if o.lead_days]
    window_days = float(np.median(leads)) if leads else ANNUAL_DAYS

    iso = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True, out_of_bounds="clip")
    iso.fit(scores, events)

    provenance = {
        "method": "isotonic_outcome_feedback",
        "n_samples": n,
        "n_events": n_events,
        "score_min": float(scores.min()),
        "score_max": float(scores.max()),
        "window_days": window_days,
        "base_rate": round(n_events / n, 4),
    }
    return CalibratedLossCurve(iso, window_days, provenance)


# ── DB adapter ───────────────────────────────────────────────────────────────

_OUTCOME_SQL = """
    SELECT CAST(predicted_score AS FLOAT) AS predicted_score,
           event_occurred,
           prediction_lead_days
    FROM   outcome_feedback
    {where}
"""


def fit_from_outcome_feedback(
    session,
    *,
    hazard_type: Optional[str] = None,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    min_events: int = DEFAULT_MIN_EVENTS,
    params: PricingParams = PricingParams(),
) -> LossCurve:
    """
    Fit a loss curve from the outcome_feedback table, optionally for one hazard.
    Returns the placeholder (flagged) if the table lacks credible data — which is
    the expected state until the Outcome Feedback Service has run for a while.
    """
    from sqlalchemy import text

    where, bind = "", {}
    if hazard_type:
        where = "WHERE hazard_type = :hazard"
        bind["hazard"] = normalize_hazard(hazard_type).value

    rows = session.execute(text(_OUTCOME_SQL.format(where=where)), bind).mappings().all()
    observations = [
        Observation(
            predicted_score=r["predicted_score"],
            event_occurred=bool(r["event_occurred"]),
            lead_days=r["prediction_lead_days"],
        )
        for r in rows
    ]
    return fit_loss_curve(
        observations, min_samples=min_samples, min_events=min_events, params=params,
    )
