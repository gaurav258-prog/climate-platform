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
