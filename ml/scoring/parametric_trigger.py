"""
Parametric insurance: "automatic payout the moment real data crosses a
threshold" -- no loss adjuster, no claims process, just an index (here, the
platform's own 0-100 hazard score for the policy's configured trigger
hazard) crossing a pre-agreed band.

payout_pct uses the standard cat-bond/parametric-cover payout curve shape:
0% below the attachment point, scaling LINEARLY up to 100% at the exhaustion
point, 100% beyond it. This is the same real convention already named in
ml/scoring/insurance_pricing.py's docstring (there, contrasted with
Loss-curve pricing's continuous damage-ratio curve) -- parametric cover is
deliberately a simpler, faster-to-pay instrument than indemnity insurance,
and a real "attachment/exhaustion" band is how that simplicity is actually
built in the reinsurance/cat-bond market.
"""
from __future__ import annotations


def payout_pct(score: float | None, attachment: float, exhaustion: float) -> float:
    if score is None or exhaustion <= attachment:
        return 0.0
    if score < attachment:
        return 0.0
    if score >= exhaustion:
        return 100.0
    return round(100.0 * (score - attachment) / (exhaustion - attachment), 1)


def trigger_block(hazard_type: str, current_score: float | None, attachment: float, exhaustion: float,
                   sum_insured_eur: float | None, updated_by: str | None = None, updated_at=None) -> dict:
    pct = payout_pct(current_score, attachment, exhaustion)
    return {
        "hazard_type": hazard_type,
        "attachment_score": attachment,
        "exhaustion_score": exhaustion,
        "current_score": current_score,
        "is_triggered": pct > 0,
        "payout_pct": pct,
        "payout_eur": round((sum_insured_eur or 0) * pct / 100.0, 2),
        "updated_by": updated_by,
        "updated_at": updated_at,
    }
