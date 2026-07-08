"""
Banking's lending-decision output: "given this collateral's physical-climate
risk, how much should we discount its value for loan-sizing purposes."
bank_assets/v_bank_asset_physical_risk previously stopped at a risk score --
no valuation-discount concept existed anywhere in the schema.

RECOMMENDED_DISCOUNT_PCT is a disclosed haircut-by-risk-bucket schedule, a
real rule-of-thumb consistent with the range published climate-stress-test
collateral-haircut guidance uses (0-30%+ depending on severity) -- NOT a
fitted or regulator-mandated figure for any specific institution. The system
RECOMMENDS; a human with pricing.approve makes the final call and can
override it (see api/routers/bank.py's valuation-override endpoint) --
override wins over the recommendation, and every override is audited via
access_audit_log (api/services/rbac.py write_audit), never silently applied.

PERIL_DISCOUNT_PCT is an OPT-IN alternative (org_calc_settings.severity_model
= 'peril_specific') that varies the haircut by which hazard actually drove
the bucket -- a wildfire VH plot (real total-loss risk to the structure) is
not the same economic event as a drought VH plot (crop/water stress, no
structural damage). Same disclosure standard as the universal table: these
are illustrative relative-severity multipliers consistent with published
physical-risk literature (structural/total-loss perils like seismic/volcanic/
wildfire skew higher; chronic/non-structural perils like drought/heat/
pollution skew lower), NOT a fitted or regulator-mandated schedule. Every org
gets the universal table unless it explicitly opts in -- see
services/calc_settings.py.
"""
from __future__ import annotations

RECOMMENDED_DISCOUNT_PCT = {"L": 0.0, "M": 5.0, "H": 15.0, "VH": 30.0}

PERIL_DISCOUNT_PCT = {
    "seismic":       {"L": 0.0, "M": 8.0, "H": 25.0, "VH": 45.0},
    "volcanic":      {"L": 0.0, "M": 8.0, "H": 25.0, "VH": 45.0},
    "wildfire":      {"L": 0.0, "M": 6.0, "H": 20.0, "VH": 38.0},
    "flood":         {"L": 0.0, "M": 5.0, "H": 18.0, "VH": 32.0},
    "storm":         {"L": 0.0, "M": 5.0, "H": 16.0, "VH": 30.0},
    "drought":       {"L": 0.0, "M": 3.0, "H": 8.0,  "VH": 15.0},
    "heat_acute":    {"L": 0.0, "M": 3.0, "H": 8.0,  "VH": 15.0},
    "heat_chronic":  {"L": 0.0, "M": 3.0, "H": 8.0,  "VH": 15.0},
    "pollution":     {"L": 0.0, "M": 2.0, "H": 5.0,  "VH": 10.0},
}


def recommended_discount_pct(bucket: str | None, hazard: str | None = None,
                              severity_model: str = "universal") -> float:
    if bucket is None:
        return 0.0
    if severity_model == "peril_specific" and hazard in PERIL_DISCOUNT_PCT:
        return PERIL_DISCOUNT_PCT[hazard].get(bucket, 0.0)
    return RECOMMENDED_DISCOUNT_PCT.get(bucket, 0.0)


def effective_discount_pct(bucket: str | None, override_pct: float | None,
                            hazard: str | None = None, severity_model: str = "universal") -> float:
    """Override wins if present (a human decision beats the recommendation);
    otherwise fall back to the bucket's (optionally peril-specific) recommended haircut."""
    if override_pct is not None:
        return float(override_pct)
    return recommended_discount_pct(bucket, hazard, severity_model)


def ltv_pct(outstanding_balance_eur: float | None, value_eur: float | None) -> float | None:
    """Loan-to-value: the actual credit-decision number a real loan tape exists to
    support. None (not 0) when we don't have an outstanding balance -- honest
    absence, never a fabricated ratio."""
    if outstanding_balance_eur is None or not value_eur:
        return None
    return round(100 * outstanding_balance_eur / value_eur, 2)


def valuation_block(bucket: str | None, value_eur: float | None, override_row: dict | None,
                     outstanding_balance_eur: float | None = None,
                     hazard: str | None = None, severity_model: str = "universal") -> dict:
    """override_row: {override_discount_pct, overridden_by, overridden_at, reason} or None.
    hazard/severity_model: pass the driving hazard + the org's chosen severity_model
    (services/calc_settings.py) to price a wildfire VH differently from a drought VH;
    omit either to get today's universal bucket->discount% table, unchanged."""
    recommended = recommended_discount_pct(bucket, hazard, severity_model)
    override_pct = override_row["override_discount_pct"] if override_row else None
    effective = effective_discount_pct(bucket, override_pct, hazard, severity_model)
    discounted_value = (value_eur or 0) * (1 - effective / 100.0)
    return {
        "recommended_discount_pct": recommended,
        "effective_discount_pct": effective,
        "is_overridden": override_pct is not None,
        "severity_model": severity_model,
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
