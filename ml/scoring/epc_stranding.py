"""Real estate's TRANSITION risk — energy-performance stranding, on the institution's stated method.

Physical risk is only half a property's climate exposure. The other half is transition: as minimum energy-performance
standards tighten, a building with a poor energy-performance certificate (EPC) lets or sells at a discount and needs
retrofit capital to comply. Neither the discount nor the capex is a fact the platform holds — no EU text sets an EPC
grade below which a building loses a stated share of its value — so both are the institution's own statement, per EPC
grade (E69): method.brown_discount and method.retrofit_capex_share (data/reference/money/parameters.json). A grade the
institution does not discount is stated as 0. The platform supplies no default: a property whose grade has no stated
value is a named gap, and the book total over it is a gap, never a partial sum.

A property with no EPC on record, or no value, cannot be assessed; it is counted as coverage, never given a number.
"""
from __future__ import annotations

from typing import Optional

# EPC grades best → worst (the certificate's own scale)
EPC_ORDER = ["A", "B", "C", "D", "E", "F", "G"]
EPC_RANK = {g: i for i, g in enumerate(EPC_ORDER)}


def _grade(epc_rating: Optional[str]) -> Optional[str]:
    g = (epc_rating or "").strip().upper()
    return g if g in EPC_RANK else None


def epc_stranding(method, epc_rating: Optional[str], property_value_eur: Optional[float],
                  annual_noi_eur: Optional[float] = None) -> dict:
    """One property: the stated brown-value discount of its EPC grade, the value it takes, the retrofit capex and the
    NOI it puts at risk — or 'not assessed' (no EPC / no value), or a gap (the grade's discount or capex not stated)."""
    grade = _grade(epc_rating)
    if grade is None:
        return {"assessed": False, "reason": "no_epc",
                "note": "No EPC on record — energy-performance stranding cannot be assessed for this property."}
    if not property_value_eur:
        return {"assessed": False, "reason": "no_value", "epc_rating": grade,
                "note": "No value on record — the stranding of this property cannot be computed."}
    discount = method.get("method.brown_discount", grade)
    capex_share = method.get("method.retrofit_capex_share", grade)
    if discount is None or capex_share is None:
        missing = [k for k, v in (("method.brown_discount", discount), ("method.retrofit_capex_share", capex_share)) if v is None]
        return {"assessed": True, "epc_rating": grade, "gap": "not stated: " + ", ".join(f"{k} ({grade})" for k in missing)}
    return {
        "assessed": True, "epc_rating": grade, "discounted": discount > 0,
        "brown_discount_pct": round(100 * discount, 2),
        "value_at_risk_eur": round(property_value_eur * discount, 2),
        "retrofit_capex_eur": round(property_value_eur * capex_share, 2),
        "noi_at_risk_eur": round(annual_noi_eur * discount, 2) if annual_noi_eur else None,
        "note": (f"EPC {grade}: the stated brown discount is {round(100 * discount, 2)}% of value and the stated "
                 f"retrofit capex {round(100 * capex_share, 2)}% of value (the institution's method)."),
    }


def loan_collateral_stranding(method, epc_rating: Optional[str], collateral_value_eur: Optional[float],
                              loan_eur: Optional[float]) -> dict:
    """A bank's transition risk on ONE real-estate-collateralised loan: the stated discount erodes the collateral,
    lifting the effective LTV; the loan value the stressed collateral no longer covers is at risk (an LGD driver)."""
    st = epc_stranding(method, epc_rating, collateral_value_eur)
    if not st["assessed"] or st.get("gap"):
        return st
    if not loan_eur:
        return {"assessed": False, "reason": "no_outstanding", "epc_rating": st["epc_rating"],
                "note": "No outstanding balance on record — the loan value at risk cannot be computed."}
    discount = st["brown_discount_pct"] / 100
    stressed = collateral_value_eur * (1 - discount)
    return {
        "assessed": True, "epc_rating": st["epc_rating"], "discounted": st["discounted"],
        "brown_discount_pct": st["brown_discount_pct"],
        "collateral_value_at_risk_eur": st["value_at_risk_eur"],
        "original_ltv_pct": round(100 * loan_eur / collateral_value_eur, 1),
        "stressed_ltv_pct": round(100 * loan_eur / stressed, 1) if stressed else None,
        "loan_value_at_risk_eur": round(max(0.0, loan_eur - stressed), 2),
        "retrofit_capex_eur": st["retrofit_capex_eur"],
    }


def _gaps(results: list[dict]) -> Optional[str]:
    g = sorted({r["gap"] for r in results if r.get("gap")})
    return "; ".join(g) if g else None


def bank_collateral_stranding_rollup(method, loans: list[dict]) -> dict:
    """Book-level collateral energy-stranding for the bank's real-estate-collateralised loans (rows: epc_label,
    asset_value_eur = collateral, outstanding_loan_balance_eur). A gap in any assessed loan makes the totals a gap."""
    res = [(x, loan_collateral_stranding(method, x.get("epc_label"), x.get("asset_value_eur"),
                                         x.get("outstanding_loan_balance_eur"))) for x in loans]
    n = len(loans)
    assessed = [(x, r) for x, r in res if r["assessed"]]
    base = {"n_re_loans": n, "n_assessed": len(assessed), "n_not_assessed": n - len(assessed),
            "epc_coverage_pct": round(100 * len(assessed) / n, 1) if n else None}
    gap = _gaps([r for _, r in assessed])
    if gap:
        return {**base, "gap": gap}
    disc = [(x, r) for x, r in assessed if r["discounted"]]
    exposure = sum(x["outstanding_loan_balance_eur"] for x, _ in assessed)
    w_orig = sum(r["original_ltv_pct"] * x["outstanding_loan_balance_eur"] for x, r in assessed)
    w_stress = sum(r["stressed_ltv_pct"] * x["outstanding_loan_balance_eur"] for x, r in assessed if r["stressed_ltv_pct"] is not None)
    stressed_complete = all(r["stressed_ltv_pct"] is not None for _, r in assessed)
    orig = round(w_orig / exposure, 1) if exposure else None
    stress = round(w_stress / exposure, 1) if exposure and stressed_complete else None
    below = sum(x["outstanding_loan_balance_eur"] for x, _ in disc)
    return {
        **base,
        "n_discounted": len(disc),
        "collateral_value_at_risk_eur": round(sum(r["collateral_value_at_risk_eur"] for _, r in disc)),
        "loan_value_at_risk_eur": round(sum(r["loan_value_at_risk_eur"] for _, r in disc)),
        "retrofit_capex_to_derisk_eur": round(sum(r["retrofit_capex_eur"] for _, r in disc)),
        "exposure_weighted_ltv_pct": orig, "stressed_ltv_pct": stress,
        "ltv_uplift_pp": round(stress - orig, 1) if orig is not None and stress is not None else None,
        "exposure_discounted_eur": round(below),
        "pct_exposure_discounted": round(100 * below / exposure, 1) if exposure else None,
        "note": ("Transition risk on the bank's real-estate collateral: the institution's stated brown discount per EPC "
                 "grade erodes the collateral, lifting the effective LTV; the loan value the stressed collateral no "
                 "longer covers is at risk (an LGD driver). Loans without an EPC, a collateral value or an outstanding "
                 "balance are counted as not assessed, never given a number."),
    }


def stranding_rollup(method, properties: list[dict]) -> dict:
    """Portfolio energy-stranding on the stated method: € value at risk, retrofit capex and coverage. Rows expose
    epc_rating, property_value_eur, annual_noi_eur. A gap in any assessed property makes the totals a gap."""
    res = [(p, epc_stranding(method, p.get("epc_rating"), p.get("property_value_eur"), p.get("annual_noi_eur")))
           for p in properties]
    n = len(properties)
    assessed = [(p, r) for p, r in res if r["assessed"]]
    base = {"n_properties": n, "n_assessed": len(assessed), "n_not_assessed": n - len(assessed),
            "epc_coverage_pct": round(100 * len(assessed) / n, 1) if n else None}
    gap = _gaps([r for _, r in assessed])
    if gap:
        return {**base, "gap": gap}
    disc = [(p, r) for p, r in assessed if r["discounted"]]
    total_value = sum(p["property_value_eur"] for p, _ in assessed)
    value_disc = sum(p["property_value_eur"] for p, _ in disc)
    return {
        **base,
        "n_discounted": len(disc),
        "value_at_stranding_risk_eur": round(sum(r["value_at_risk_eur"] for _, r in disc)),
        "retrofit_capex_to_derisk_eur": round(sum(r["retrofit_capex_eur"] for _, r in disc)),
        "pct_assessed_value_discounted": round(100 * value_disc / total_value, 1) if total_value else None,
        "note": ("Energy-performance stranding on the institution's stated brown discount and retrofit capex per EPC "
                 "grade. Properties without an EPC or a value are counted as not assessed, never given a number."),
    }
