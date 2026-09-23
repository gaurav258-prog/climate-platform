"""Solvency II — SCR Non-Life catastrophe risk (template S.26.01.01), natural-catastrophe sub-module.

Regulation: Commission Delegated Regulation (EU) 2015/35 (Solvency II), Title I Chapter V Section 2
(catastrophe risk); reported on QRT S.26.01.01. The insurer snapshot already runs one correlated cat
distribution and carries `solvency_scr`, `reinsurance` and `by_hazard`; this maps them into the S.26.01
natural-catastrophe structure — it does not re-run anything.

Honesty discipline (same as the banking Pillar 3 build): we report our INTERNAL-MODEL NatCat SCR (the modelled
1-in-200 / 99.5 % VaR annual-aggregate loss, gross and net of the illustrative reinsurance programme) and the
per-peril exposure that drives it, ALONGSIDE the PRESCRIBED STANDARD-FORMULA NatCat SCR — all five sub-modules
(windstorm, earthquake, flood, hail, subsidence), computed from EIOPA's own per-region factors (Del. Reg.
2015/35, Art. 120-125 and Annexes V-VIII — see services/governance/solvency2_natcat.py). Both bases are cited
and labelled. The only remaining external dependency is intra-country: the EXACT zonal SCR (Annex IX risk
zones) needs postcode/administrative boundary geodata to assign each location to its zone — a bounded,
declared external dependency, like the bank's EBA DPM binding, not the aggregate SCR itself.

GROUP-SCOPE HONESTY (C3, 2026-09-23 independent consolidation-scope review): when this is computed for a
consolidated (parent/group) scope, what's built is a NatCat sub-module figure on the ownership-weighted POOL
of the group's policies — ONE Basic SCR module (catastrophe risk), not a Solvency II Title III group solvency
position. Real group supervision (Arts 218-243) needs either Method 1 (Art 230: accounting-consolidation
basis — group eligible own funds minus a group SCR computed from the FULL Basic SCR module set: market,
health, life, non-life underwriting, default, catastrophe, aggregated through the Art 104 correlation matrix)
or Method 2 (Art 233: deduction and aggregation — parent's solo SCR plus its proportional share of each
related undertaking's own solo SCR, which does NOT capture diversification benefit). Neither group own funds,
the other Basic SCR modules, nor the Art 230/233 aggregation formula exist in this codebase — this function
computes one input a Method 1/2 calculation would need, not the calculation itself. s2601_natcat() discloses
this explicitly via `group_method_note` whenever `group_scope=True`; it never silently presents the pooled
NatCat SCR as a group solvency figure.
"""
from __future__ import annotations

# our hazard channel -> the Solvency II S.26.01 natural-catastrophe peril line
_S2601_PERIL = {
    "windstorm": "Windstorm", "storm": "Windstorm",
    "flood": "Flood", "coastal_flood": "Flood",
    "seismic": "Earthquake",
    "severe_convective": "Hail",
    "subsidence": "Subsidence",
}


def s2601_natcat(snapshot: dict, group_scope: bool = False) -> dict:
    """Build the S.26.01.01 natural-catastrophe block from a frozen insurer disclosure snapshot.

    group_scope=True means this was computed over an ownership-weighted pool of a group's subtree (see the
    module docstring's GROUP-SCOPE HONESTY note) — stamps group_method_note disclosing that this is one
    Basic SCR sub-module on the consolidated exposure, not a Title III Method 1/2 group solvency position."""
    scr = snapshot.get("solvency_scr") or {}
    reins = snapshot.get("reinsurance") or {}
    by_hazard = snapshot.get("by_hazard") or {}

    if not scr.get("available", True) or scr.get("natcat_scr_eur") is None:
        return {"framework": "insurer_solvency", "available": False,
                "reason": scr.get("reason", "no scored policies to run the catastrophe distribution"),
                "regulation": "Commission Delegated Regulation (EU) 2015/35, S.26.01.01"}

    # per-peril exposure that drives the aggregate NatCat SCR (from the already-computed accumulation)
    perils: dict[str, dict] = {}
    for hz, agg in by_hazard.items():
        peril = _S2601_PERIL.get(hz)
        if not peril:
            continue
        row = perils.setdefault(peril, {"peril": peril, "exposed_value_eur": 0.0, "n_exposed": 0, "channels": []})
        row["exposed_value_eur"] += agg.get("exposed_value_eur") or 0
        row["n_exposed"] += agg.get("n_exposed") or 0
        row["channels"].append(hz)
    peril_rows = sorted(perils.values(), key=lambda r: -r["exposed_value_eur"])
    for r in peril_rows:
        r["exposed_value_eur"] = round(r["exposed_value_eur"])

    gross = scr.get("natcat_scr_eur")
    # net NatCat SCR = the net-of-reinsurance annual-aggregate 1-in-200 (same AEP basis as the gross SCR)
    net = ((reins.get("net") or {}).get("net_aep_eur") or {}).get("rp_200")
    group_method_note = None
    if group_scope:
        group_method_note = {
            "status": "not_a_group_solvency_position",
            "note": "This figure is the catastrophe-risk sub-module SCR on an ownership-weighted pool of the "
                    "group's policies — ONE Basic SCR module, computed over consolidated exposure. It is NOT a "
                    "Solvency II Title III group solvency position: no group eligible own funds, no other "
                    "Basic SCR modules (market/health/life/non-life underwriting/default), and neither the "
                    "Method 1 consolidation-basis formula (Art 230) nor the Method 2 deduction-and-aggregation "
                    "formula (Art 233) is applied. Use this as one input into a real group-SCR calculation, "
                    "not as that calculation's result.",
            "regulation": "Directive 2009/138/EC (Solvency II) Title III, Arts 218-243 — group supervision",
        }
    return {
        "framework": "insurer_solvency",
        "regulation": "Commission Delegated Regulation (EU) 2015/35 — SCR Non-Life catastrophe risk (S.26.01.01)",
        "basis": scr.get("scr_basis", "internal_model_99_5_var"),
        "group_method_note": group_method_note,
        "natcat_scr": {
            "gross_1_in_200_eur": round(gross) if gross is not None else None,
            "net_of_reinsurance_1_in_200_eur": round(net) if net is not None else None,
            "mean_annual_loss_eur": scr.get("mean_annual_loss_eur"),
            "risk_load_eur": scr.get("risk_load_eur"),
            "scr_pct_of_sum_insured": scr.get("scr_pct_of_sum_insured"),
        },
        "perils": peril_rows,          # the natural-catastrophe sub-module lines driving the aggregate
        "note": scr.get("note"),
        # prescribed STANDARD-FORMULA NatCat SCR — all five sub-modules from EIOPA's own factors (Art. 120-125), cited
        "standard_formula_natcat": scr.get("standard_formula_natcat"),
        # what is still declared-external rather than computed
        "declared": {
            "status": "declared_external",
            "items": ["Intra-country risk-zone weights & diversification (Annex IX/X/XXII-XXVI) for the EXACT zonal "
                      "figure — needs postcode/administrative boundary geodata to assign each location to its zone",
                      "Man-made catastrophe sub-modules (out of climate scope)"],
            "note": "All five nat-cat standard-formula sub-modules (windstorm, earthquake, flood, hail, subsidence) "
                    "are computed above from the official OJ Annex factors (cited), at country level, INCLUDING the "
                    "Art. 123(7)/124(7) flood/hail motor term where present. The only remaining approximation is "
                    "intra-country: the exact zonal SCR needs external boundary geodata to map locations to the "
                    "Annex IX risk zones — a bounded external dependency, like the bank EBA DPM binding.",
        },
    }
