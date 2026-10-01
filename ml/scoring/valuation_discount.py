"""Climate-adjusted value: how much an institution discounts an asset's (collateral) value for physical climate risk,
and what that means for loan-to-value, a portfolio's value-loss band and an asset manager's Monte-Carlo VaR.

The discount is the institution's own: its stated valuation haircut for the asset's headline peril and hazard band
(ml.scoring.damage_function, method parameter method.valuation_haircut), or — per asset — a human override (a person
with pricing.approve; audited). With neither, the climate-adjusted value is a named gap, never computed from a default.
"""
from __future__ import annotations

from ml.scoring.damage_function import DAMAGE_FUNCTION_VERSION, valuation_haircut

VAR_QUANTILES = (50, 95, 99)       # the median and the two tail quantiles the VaR reports
VAR_SIMULATIONS = 10000            # Monte-Carlo draws per VaR (a setting of the computation, seeded — audit T2)


def ltv_pct(outstanding_balance_eur: float | None, value_eur: float | None) -> float | None:
    """Loan-to-value: None (not 0) when we don't have an outstanding balance — honest absence."""
    if outstanding_balance_eur is None or not value_eur:
        return None
    return round(100 * outstanding_balance_eur / value_eur, 2)


def valuation_block(method, bucket: str | None, value_eur: float | None, override_row: dict | None,
                    outstanding_balance_eur: float | None = None, hazard: str | None = None,
                    score: float | None = None) -> dict:
    """override_row: {override_discount_pct, overridden_by, overridden_at, reason} or None. The recommended discount is
    the institution's stated haircut for (hazard, band of score); a gap when it is not stated (and no override)."""
    hc = valuation_haircut(method, hazard, score)
    recommended = None if hc is None else round(100 * hc, 4)
    override_pct = override_row["override_discount_pct"] if override_row else None
    effective = float(override_pct) if override_pct is not None else recommended
    discounted = None if effective is None or value_eur is None else (value_eur or 0) * (1 - effective / 100.0)
    gap = None
    if effective is None and hazard is not None and score is not None:
        gap = f"method.valuation_haircut ({hazard}/{bucket}) not stated"
    return {
        "recommended_discount_pct": recommended,
        "effective_discount_pct": effective,
        "is_overridden": override_pct is not None,
        "damage_function_version": DAMAGE_FUNCTION_VERSION,
        "discounted_value_eur": None if discounted is None else round(discounted, 2),
        "outstanding_loan_balance_eur": outstanding_balance_eur,
        "original_ltv_pct": ltv_pct(outstanding_balance_eur, value_eur),
        "climate_adjusted_ltv_pct": None if discounted is None else ltv_pct(outstanding_balance_eur, discounted),
        **({"gap": gap} if gap else {}),
        "override": {
            "discount_pct": override_pct,
            "overridden_by": override_row.get("overridden_by") if override_row else None,
            "overridden_at": override_row.get("overridden_at") if override_row else None,
            "reason": override_row.get("reason") if override_row else None,
        } if override_row else None,
    }


def effective_haircut(method, a: dict) -> float | None:
    """An asset's effective discount as a share: its override, else the stated haircut for its headline peril."""
    val = a.get("valuation") or {}
    if val.get("is_overridden"):
        return (val.get("effective_discount_pct") or 0) / 100.0
    return valuation_haircut(method, a.get("hazard") or a.get("headline_hazard"),
                             a.get("score") if a.get("score") is not None else a.get("headline_score"))


def monte_carlo_var(method, holdings: list[dict], org_id: str, scenario: str, horizon: str, n_sims: int) -> dict:
    """holdings: [{position_value_eur, hazard, score, valuation?}, ...]. Samples each holding's loss share from a
    triangular distribution around its own discount, the band being the institution's stated relative uncertainty
    (method.var_relative_uncertainty). Deterministic across processes (audit T2). A gap when the uncertainty or any
    scored holding's discount is not stated."""
    import hashlib

    import numpy as np

    rel = method.get("method.var_relative_uncertainty")
    means = [(h.get("position_value_eur") or 0.0, effective_haircut(method, h)) for h in holdings
             if (h.get("position_value_eur") or 0) and (h.get("score") is not None or (h.get("valuation") or {}).get("is_overridden"))]
    if rel is None or any(m is None for _, m in means):
        return {"median_loss_eur": None, "var95_eur": None, "var99_eur": None, "n_sims": n_sims,
                "gap": method.gap_text()}
    seed = int.from_bytes(hashlib.sha256(f"{org_id}|{scenario}|{horizon}".encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    losses = np.zeros(n_sims)
    for value, mean in means:
        low, high = max(0.0, mean * (1 - rel)), min(1.0, mean * (1 + rel))
        losses += (rng.triangular(low, mean, high, size=n_sims) if high > low else mean) * value
    p50, p95, p99 = np.percentile(losses, VAR_QUANTILES)
    return {"median_loss_eur": round(float(p50), 2), "var95_eur": round(float(p95), 2), "var99_eur": round(float(p99), 2),
            "n_sims": n_sims, "relative_uncertainty": rel}


def value_loss_band(method, assets: list[dict]) -> dict:
    """The portfolio's value loss (Σ value × discount) with the range the score's own confidence interval gives: each
    asset's discount read at the bands of ci_lo and ci_hi as well as at its score. An overridden asset carries its fixed
    human-set loss. A gap when a scored asset's discount is not stated."""
    point = low = high = 0.0
    banded_value = at_risk_value = 0.0
    for a in assets:
        value = (a.get("value_eur") or a.get("property_value_eur")
                 or a.get("position_value_eur") or a.get("primary_value_eur") or 0)
        score, hazard = a.get("headline_score"), a.get("headline_hazard")
        if not value or score is None:
            continue
        at_risk_value += value
        mean = effective_haircut(method, a)
        if mean is None:
            return {"expected_value_loss_eur": None, "loss_low_eur": None, "loss_high_eur": None,
                    "gap": method.gap_text(), "damage_function_version": DAMAGE_FUNCTION_VERSION}
        point += value * mean
        ci = next((h for h in (a.get("hazards") or []) if h.get("hazard") == hazard), None)
        if not (a.get("valuation") or {}).get("is_overridden") and ci and ci.get("ci_lo") is not None and ci.get("ci_hi") is not None:
            lo, hi = valuation_haircut(method, hazard, ci["ci_lo"]), valuation_haircut(method, hazard, ci["ci_hi"])
            if lo is None or hi is None:
                return {"expected_value_loss_eur": None, "loss_low_eur": None, "loss_high_eur": None,
                        "gap": method.gap_text(), "damage_function_version": DAMAGE_FUNCTION_VERSION}
            low += value * min(lo, hi)
            high += value * max(lo, hi)
            banded_value += value
        else:
            low += value * mean
            high += value * mean
    return {
        "expected_value_loss_eur": round(point), "loss_low_eur": round(low), "loss_high_eur": round(high),
        "band_pct": round(100 * (high - low) / point, 1) if point else None,
        "ci_coverage_pct": round(100 * banded_value / at_risk_value, 1) if at_risk_value else 0,
        "method": "each asset's stated valuation haircut read at the band of its score and of the ends of the score's "
                  "confidence interval; overrides carried fixed (no band)",
        "damage_function_version": DAMAGE_FUNCTION_VERSION,
    }
