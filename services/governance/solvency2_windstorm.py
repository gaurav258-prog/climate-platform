"""Solvency II standard-formula WINDSTORM CAT sub-module (Del. Reg. (EU) 2015/35, Art. 121 + Annex V).

Thin wrapper over the general nat-cat engine (services/governance/solvency2_natcat.py) — kept as a stable public
entry point for the insurance snapshot, the S.26.01 mapping and the filing form. The prescribed method, the
official Annex V factors and the disclosed country-level approximation all live in the general engine; this maps
its output onto the windstorm-specific field names those callers use.
"""
from __future__ import annotations

from services.governance.solvency2_natcat import standard_formula_peril

_APPROX = ("Country-level: one windstorm zone per region, risk weight W=1, perfect within-country correlation "
           "(WSI_r = Σ sum insured in region r). Q(windstorm,r) and the inter-region correlation are the EXACT "
           "Annex V values; the intra-country Annex IX/X/XXII zone risk-weights and zone-diversification are not "
           "applied. Approximation, not the exact zonal figure; gross of reinsurance.")


def standard_formula_windstorm(policies: list[dict]) -> dict:
    """Prescribed Solvency II standard-formula windstorm CAT SCR (gross of reinsurance) — see solvency2_natcat."""
    r = standard_formula_peril(policies, "windstorm")
    if not r.get("available"):
        return {"available": False, "reason": r.get("reason", "windstorm region exposure unavailable"),
                "other_regions_sum_insured_eur": r.get("other_regions_sum_insured_eur", 0),
                "citation": r.get("citation", "Del. Reg. (EU) 2015/35, Art. 121 + Annex V")}
    return {
        "available": True, "basis": r["basis"], "gross_of_reinsurance": True,
        "scr_windstorm_eur": r["scr_eur"],
        "undiversified_scr_eur": r["undiversified_scr_eur"],
        "regional_diversification_benefit_eur": r["regional_diversification_benefit_eur"],
        "per_region": [{"region": pr["region"], "region_name": pr["region_name"],
                        "sum_insured_eur": pr["sum_insured_eur"], "n_policies": pr["n_policies"],
                        "windstorm_factor_q": pr["risk_factor_q"], "scr_windstorm_region_eur": pr["scr_region_eur"]}
                       for pr in r["per_region"]],
        "n_regions": r["n_regions"], "other_regions_sum_insured_eur": r["other_regions_sum_insured_eur"],
        "scenario_gross_factor": r["gross_factor"], "citation": r["citation"],
        "params_version": r.get("params_version"), "approximation": _APPROX,
        "method": ("SCR_windstorm = sqrt(ΣΣ CorrWS(r,s)·SCR_r·SCR_s), SCR_r = 1.20·Q_r·SI_r "
                   "(Art.121(1),(2),(5); scenarios A and B both give 1.20·L gross)."),
    }
