"""Real estate's TRANSITION risk — energy-performance stranding.

Physical risk is only half a property's climate exposure. The other half is transition: as minimum
energy-performance standards tighten (the EU EPBD recast's rising floor; national MEES-style rules), a building
below the legal floor faces a "brown discount" — it lets/sells at a discount, risks becoming un-lettable, and
needs retrofit capital to comply. Banking already prices transition risk on its book; this gives the REIT the
same missing dimension, expressed on the property's own value and NOI.

HONEST BY CONSTRUCTION. This is a disclosed PARAMETRIC POLICY SCENARIO, not a fitted market model — the floor
year/grade and the per-grade discount/capex coefficients are stated openly (and are governable, like the other
interpretation switches), never presented as an observed market fit. A property with no EPC on record is
flagged as un-assessable, never assigned a fabricated stranding number.
"""
from __future__ import annotations

from typing import Optional

# EPC grades best → worst; rank 0 = A (best)
EPC_ORDER = ["A", "B", "C", "D", "E", "F", "G"]
EPC_RANK = {g: i for i, g in enumerate(EPC_ORDER)}

# Disclosed parametric coefficients — a POLICY SCENARIO, not a market fit.
_BROWN_DISCOUNT_PER_GRADE = 0.03   # value discount per EPC grade below the floor
_MAX_DISCOUNT = 0.20               # cap the modelled discount
_RETROFIT_CAPEX_PER_GRADE = 0.04   # retrofit capex as a share of value, per grade to lift toward the floor
_DEFAULT_FLOOR_EPC = "D"           # a widely-signalled 2030s minimum-to-let (EPBD-recast direction); configurable


def epc_stranding(epc_rating: Optional[str], property_value_eur: Optional[float],
                  annual_noi_eur: Optional[float] = None, floor_epc: str = _DEFAULT_FLOOR_EPC) -> dict:
    """Per-property energy-performance stranding under a rising minimum-EPC floor. Returns the brown-value
    discount, the retrofit capex to reach the floor, and the NOI at risk of un-lettability — or an honest
    'not assessed' when no EPC is on record."""
    floor = floor_epc if floor_epc in EPC_RANK else _DEFAULT_FLOOR_EPC
    value = property_value_eur or 0.0
    if not epc_rating or epc_rating.upper() not in EPC_RANK:
        return {"assessed": False, "reason": "no_epc", "floor_epc": floor,
                "note": "No EPC on record — energy-performance stranding cannot be assessed for this property. "
                        "Provide the EPC grade to enable a real transition-risk check."}
    grade = epc_rating.upper()
    grades_below = max(0, EPC_RANK[grade] - EPC_RANK[floor])
    if grades_below == 0:
        return {"assessed": True, "epc_rating": grade, "floor_epc": floor, "below_floor": False,
                "grades_below": 0, "brown_discount_pct": 0.0, "value_at_risk_eur": 0.0,
                "retrofit_capex_eur": 0.0, "noi_at_risk_eur": 0.0 if annual_noi_eur else None,
                "note": f"EPC {grade} meets the modelled {floor} floor — no stranding under this scenario."}
    discount = min(_MAX_DISCOUNT, grades_below * _BROWN_DISCOUNT_PER_GRADE)
    return {
        "assessed": True, "epc_rating": grade, "floor_epc": floor, "below_floor": True,
        "grades_below": grades_below,
        "brown_discount_pct": round(100 * discount, 2),
        "value_at_risk_eur": round(value * discount, 2),
        "retrofit_capex_eur": round(value * grades_below * _RETROFIT_CAPEX_PER_GRADE, 2),
        "noi_at_risk_eur": round((annual_noi_eur or 0.0) * discount, 2) if annual_noi_eur else None,
        "note": (f"EPC {grade} is {grades_below} grade(s) below the modelled {floor} minimum-to-let. Modelled "
                 f"brown discount {round(100 * discount, 1)}% of value; retrofit capex to reach the floor. "
                 "Disclosed policy scenario (EPBD-recast direction), not a market fit."),
    }


def loan_collateral_stranding(epc_rating: Optional[str], collateral_value_eur: Optional[float],
                              loan_eur: Optional[float], floor_epc: str = _DEFAULT_FLOOR_EPC) -> dict:
    """A bank's transition risk on ONE real-estate-collateralised loan: energy-stranding of the collateral erodes
    its value, lifting the effective LTV and, where the stressed collateral no longer covers the loan, putting
    loan value at risk (an LGD driver). Reuses the property brown-discount; honest 'not assessed' with no EPC."""
    st = epc_stranding(epc_rating, collateral_value_eur, None, floor_epc)
    if not st["assessed"]:
        return {"assessed": False, "reason": st.get("reason"), "note": st.get("note")}
    value = collateral_value_eur or 0.0
    loan = loan_eur or 0.0
    discount = (st["brown_discount_pct"] or 0.0) / 100.0
    stressed_collateral = value * (1.0 - discount)
    uncovered = max(0.0, loan - stressed_collateral)   # loan value no longer covered once the collateral strands
    return {
        "assessed": True, "epc_rating": st["epc_rating"], "floor_epc": st["floor_epc"],
        "below_floor": st["below_floor"], "grades_below": st["grades_below"],
        "brown_discount_pct": st["brown_discount_pct"],
        "collateral_value_at_risk_eur": st["value_at_risk_eur"],
        "original_ltv_pct": round(100 * loan / value, 1) if value else None,
        "stressed_ltv_pct": round(100 * loan / stressed_collateral, 1) if stressed_collateral else None,
        "loan_value_at_risk_eur": round(uncovered, 2),
        "retrofit_capex_eur": st["retrofit_capex_eur"],
    }


def bank_collateral_stranding_rollup(loans: list[dict], floor_epc: str = _DEFAULT_FLOOR_EPC) -> dict:
    """Book-level collateral energy-stranding for a bank's real-estate-collateralised loans. `loans` rows expose
    epc_label, asset_value_eur (collateral), outstanding_loan_balance_eur (loan)."""
    n = len(loans)
    below = 0
    no_epc = 0
    loan_var = capex = collat_var = 0.0
    loan_below = 0.0
    total_loan = 0.0
    # exposure-weighted LTV migration (the LGD driver even where the loan stays covered)
    w_orig_ltv = w_stress_ltv = w_exposure = 0.0
    for x in loans:
        loan = x.get("outstanding_loan_balance_eur") or x.get("loan_eur") or 0.0
        total_loan += loan
        r = loan_collateral_stranding(x.get("epc_label") or x.get("epc_rating"),
                                      x.get("asset_value_eur") or x.get("collateral_value_eur"), loan, floor_epc)
        if not r["assessed"]:
            no_epc += 1
            continue
        if r["original_ltv_pct"] is not None and r["stressed_ltv_pct"] is not None and loan:
            w_orig_ltv += r["original_ltv_pct"] * loan
            w_stress_ltv += r["stressed_ltv_pct"] * loan
            w_exposure += loan
        if r["below_floor"]:
            below += 1
            loan_var += r["loan_value_at_risk_eur"]
            collat_var += r["collateral_value_at_risk_eur"]
            capex += r["retrofit_capex_eur"]
            loan_below += loan
    orig_ltv = round(w_orig_ltv / w_exposure, 1) if w_exposure else None
    stress_ltv = round(w_stress_ltv / w_exposure, 1) if w_exposure else None
    return {
        "floor_epc": floor_epc,
        "n_re_loans": n,
        "n_assessed": n - no_epc,
        "n_no_epc": no_epc,
        "n_below_floor": below,
        "collateral_value_at_risk_eur": round(collat_var),   # recovery-cushion erosion — the LGD driver
        "loan_value_at_risk_eur": round(loan_var),           # tail: exposure uncovered once collateral strands (LTV>100%)
        "retrofit_capex_to_derisk_eur": round(capex),
        "exposure_weighted_ltv_pct": orig_ltv,
        "stressed_ltv_pct": stress_ltv,
        "ltv_uplift_pp": round(stress_ltv - orig_ltv, 1) if (orig_ltv is not None and stress_ltv is not None) else None,
        "exposure_below_floor_eur": round(loan_below),
        "pct_re_loans_below_floor": round(100 * loan_below / total_loan, 1) if total_loan else 0.0,
        "epc_coverage_pct": round(100 * (n - no_epc) / n, 1) if n else 0.0,
        "note": ("Transition risk on the bank's real-estate loan collateral: energy-performance stranding under a "
                 "rising minimum-EPC floor erodes collateral value, lifting effective LTV and putting loan value "
                 "at risk where the stressed collateral no longer covers the loan (an LGD driver). Disclosed "
                 "policy scenario (EPBD-recast direction), not a market fit; loans with no EPC are excluded and "
                 "reported as coverage, never assigned a fabricated number."),
    }


def stranding_rollup(properties: list[dict], floor_epc: str = _DEFAULT_FLOOR_EPC) -> dict:
    """Portfolio energy-stranding summary: € value at risk, retrofit capex to de-risk, and honest coverage
    (how many properties carry an EPC). `properties` rows must expose epc_rating, property_value_eur, annual_noi_eur."""
    n = len(properties)
    assessed, below, no_epc = [], [], 0
    var_total = capex_total = value_below = 0.0
    total_value = 0.0
    for p in properties:
        total_value += p.get("property_value_eur") or 0.0
        st = epc_stranding(p.get("epc_rating"), p.get("property_value_eur"), p.get("annual_noi_eur"), floor_epc)
        if not st["assessed"]:
            no_epc += 1
            continue
        assessed.append(st)
        if st["below_floor"]:
            below.append(st)
            var_total += st["value_at_risk_eur"]
            capex_total += st["retrofit_capex_eur"]
            value_below += p.get("property_value_eur") or 0.0
    return {
        "floor_epc": floor_epc,
        "n_properties": n,
        "n_assessed": len(assessed),
        "n_no_epc": no_epc,
        "n_below_floor": len(below),
        "value_at_stranding_risk_eur": round(var_total),
        "retrofit_capex_to_derisk_eur": round(capex_total),
        "pct_portfolio_value_below_floor": round(100 * value_below / total_value, 1) if total_value else 0.0,
        "epc_coverage_pct": round(100 * len(assessed) / n, 1) if n else 0.0,
        "note": ("Energy-performance stranding under a rising minimum-EPC floor — a disclosed policy scenario "
                 "(EPBD-recast direction), governable, not a market fit. Properties without an EPC on record are "
                 "excluded and reported as coverage, never assigned a fabricated number."),
    }
