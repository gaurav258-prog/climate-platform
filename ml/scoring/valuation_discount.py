"""
Banking's lending-decision output: "given this collateral's physical-climate
risk, how much should we discount its value for loan-sizing purposes."

The damage math now lives in ml/scoring/damage_function.py (the ONE hazard→€
core shared with insurance/NOI/VaR). This module keeps the banking-facing
public API — valuation_block / recommended_discount_pct / monte_carlo_var / ltv_pct
— and delegates the curve to that core, which is:

  * CONTINUOUS in the score (no more 4-bucket cliffs), interpolated through the
    same disclosed haircut schedule, so the anchor magnitudes are unchanged; and
  * VULNERABILITY-DIFFERENTIATED by the asset's own construction_type / year_built
    / number_of_stories (a bounded, literature-derived multiplier), capped at the
    peril's disclosed VH value so figures move WITHIN today's bands, never inflated.

The schedules RECOMMENDED_DISCOUNT_PCT / PERIL_DISCOUNT_PCT are re-exported from
the core for callers that still import them from here. Overrides are unchanged: a
human with pricing.approve can override the recommendation (bank.py's override
endpoint); override wins and is audited (access_audit_log) — never silently applied.

monte_carlo_var is asset management's OPT-IN alternative to the default deterministic
haircut. It Monte-Carlo-samples each holding's loss% from a triangular distribution
centered on that holding's OWN vulnerability-adjusted haircut, with a disclosed ±40%
band (not fitted), seeded deterministically from (org_id, scenario, horizon) so the
same portfolio+settings always reproduce the same figure (audit T2). Still not a
fitted or historical VaR — a disclosed modelling assumption on top of the disclosed
haircut it samples around.
"""
from __future__ import annotations

from ml.scoring.damage_function import (  # noqa: F401 — re-exported for backward-compatible imports
    DAMAGE_FUNCTION_VERSION,
    PERIL_DISCOUNT_PCT,
    RECOMMENDED_DISCOUNT_PCT,
    collateral_haircut_pct,
    vulnerability_factor,
)


def recommended_discount_pct(bucket: str | None, hazard: str | None = None,
                             severity_model: str = "universal") -> float:
    """The bucket-based recommendation (no score/attrs) — kept for legacy callers. Reproduces the
    disclosed schedule value at the bucket. valuation_block() uses the continuous, vulnerability-
    aware haircut instead."""
    return collateral_haircut_pct(None, bucket, hazard, severity_model, None)


def effective_discount_pct(bucket: str | None, override_pct: float | None,
                           hazard: str | None = None, severity_model: str = "universal") -> float:
    """Override wins if present (a human decision beats the recommendation)."""
    if override_pct is not None:
        return float(override_pct)
    return recommended_discount_pct(bucket, hazard, severity_model)


def ltv_pct(outstanding_balance_eur: float | None, value_eur: float | None) -> float | None:
    """Loan-to-value: None (not 0) when we don't have an outstanding balance — honest absence."""
    if outstanding_balance_eur is None or not value_eur:
        return None
    return round(100 * outstanding_balance_eur / value_eur, 2)


def valuation_block(bucket: str | None, value_eur: float | None, override_row: dict | None,
                    outstanding_balance_eur: float | None = None,
                    hazard: str | None = None, severity_model: str = "universal",
                    score: float | None = None, attrs: dict | None = None) -> dict:
    """override_row: {override_discount_pct, overridden_by, overridden_at, reason} or None.
    score: the headline continuous 0–100 score (drives the continuous curve; falls back to the
    bucket if omitted, unchanged). attrs: {construction_type, year_built, number_of_stories} for
    the vulnerability multiplier (a missing attribute is neutral + flagged, never guessed)."""
    recommended = collateral_haircut_pct(score, bucket, hazard, severity_model, attrs)
    override_pct = override_row["override_discount_pct"] if override_row else None
    effective = float(override_pct) if override_pct is not None else recommended
    discounted_value = (value_eur or 0) * (1 - effective / 100.0)
    vf, vprov = vulnerability_factor(hazard, attrs)
    return {
        "recommended_discount_pct": recommended,
        "effective_discount_pct": effective,
        "is_overridden": override_pct is not None,
        "severity_model": severity_model,
        "vulnerability_factor": vf,
        "vulnerability": vprov,
        "damage_function_version": DAMAGE_FUNCTION_VERSION,
        "discounted_value_eur": round(discounted_value, 2),
        "outstanding_loan_balance_eur": outstanding_balance_eur,
        "original_ltv_pct": ltv_pct(outstanding_balance_eur, value_eur),
        "climate_adjusted_ltv_pct": ltv_pct(outstanding_balance_eur, discounted_value),
        "override": {
            "discount_pct": override_pct,
            "overridden_by": override_row.get("overridden_by") if override_row else None,
            "overridden_at": override_row.get("overridden_at") if override_row else None,
            "reason": override_row.get("reason") if override_row else None,
        } if override_row else None,
    }


def monte_carlo_var(holdings: list[dict], org_id: str, scenario: str, horizon: str,
                    severity_model: str = "universal", n_sims: int = 10000,
                    relative_uncertainty: float = 0.4) -> dict:
    """holdings: [{position_value_eur, bucket, hazard, score?, attrs?}, ...]. Samples each holding's
    loss% around its OWN vulnerability-adjusted continuous haircut. Returns median/P95/P99 of a
    simulated portfolio loss distribution (EUR). Deterministic across processes (audit T2)."""
    import hashlib

    import numpy as np

    n = len(holdings)
    if n == 0:
        return {"median_loss_eur": 0.0, "var95_eur": 0.0, "var99_eur": 0.0,
                "n_sims": n_sims, "relative_uncertainty_band": relative_uncertainty}

    # Deterministic seed: builtin hash() is per-process salted, so a stable digest keeps the same
    # portfolio+settings reproducible across processes/redeploys (audit T2).
    seed = int.from_bytes(hashlib.sha256(f"{org_id}|{scenario}|{horizon}".encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)

    losses = np.zeros(n_sims)
    for h in holdings:
        value = h.get("position_value_eur") or 0.0
        if value == 0:
            continue
        mean = collateral_haircut_pct(h.get("score"), h.get("bucket"), h.get("hazard"),
                                      severity_model, h.get("attrs")) / 100.0
        spread = max(mean * relative_uncertainty, 0.02)
        low, high = max(0.0, mean - spread), min(1.0, mean + spread)
        if high <= low:
            losses += mean * value
            continue
        losses += rng.triangular(low, mean, high, size=n_sims) * value

    p50, p95, p99 = np.percentile(losses, [50, 95, 99])
    return {
        "median_loss_eur": round(float(p50), 2),
        "var95_eur": round(float(p95), 2),
        "var99_eur": round(float(p99), 2),
        "n_sims": n_sims,
        "relative_uncertainty_band": relative_uncertainty,
    }
