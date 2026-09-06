"""Solvency II — SCR Non-Life catastrophe risk (template S.26.01.01), natural-catastrophe sub-module.

Regulation: Commission Delegated Regulation (EU) 2015/35 (Solvency II), Title I Chapter V Section 2
(catastrophe risk); reported on QRT S.26.01.01. The insurer snapshot already runs one correlated cat
distribution and carries `solvency_scr`, `reinsurance` and `by_hazard`; this maps them into the S.26.01
natural-catastrophe structure — it does not re-run anything.

Honesty discipline (same as the banking Pillar 3 build): we report our INTERNAL-MODEL NatCat SCR (the modelled
1-in-200 / 99.5 % VaR annual-aggregate loss, gross and net of the illustrative reinsurance programme) and the
per-peril exposure that drives it. The PRESCRIBED STANDARD-FORMULA cells — EIOPA's per-region catastrophe
factors and CRESTA-zone weights (Del. Reg. 2015/35 Annex) — are DECLARED, not fabricated: they need the
official factor tables per country/zone, which are an external input, exactly as the bank's EBA DPM binding is.
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


def s2601_natcat(snapshot: dict) -> dict:
    """Build the S.26.01.01 natural-catastrophe block from a frozen insurer disclosure snapshot."""
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
    return {
        "framework": "insurer_solvency",
        "regulation": "Commission Delegated Regulation (EU) 2015/35 — SCR Non-Life catastrophe risk (S.26.01.01)",
        "basis": scr.get("scr_basis", "internal_model_99_5_var"),
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
            "items": ["Intra-country CRESTA-zone sum-insured weights (Annex IX/X/XXII-XXVI) for the EXACT zonal figures",
                      "Flood/hail motor sum-insured component (LoB 5/17)",
                      "Man-made catastrophe sub-modules (out of climate scope)"],
            "note": "All five nat-cat standard-formula sub-modules (windstorm, earthquake, flood, hail, subsidence) "
                    "are computed above from the official OJ Annex factors (cited), at country level. The intra-"
                    "country zonal refinement and the motor component need further official Annex tables / data.",
        },
    }
