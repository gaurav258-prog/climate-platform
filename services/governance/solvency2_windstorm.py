"""Solvency II STANDARD-FORMULA windstorm catastrophe sub-module (Del. Reg. (EU) 2015/35, Article 121).

This is a PRESCRIBED regulatory calculation, not a model: it applies EIOPA's own per-region windstorm factors
Q(windstorm,r) and the windstorm region-correlation matrix CorrWS(r,s) (both verbatim from Annex V, loaded from
data/reference/solvency2_windstorm_annex_v.json) to the insurer's sums insured. Because the coefficients are the
regulator's, cited to the Official Journal, this passes the honesty gate as a prescribed calc — it is NOT our
own hazard model and does NOT depend on the (screening-tier) windstorm hazard score.

Method (Art. 121), gross of reinsurance:
  L(windstorm,r)      = Q(windstorm,r) · WSI_r                       — specified windstorm loss in region r  [Art.121(5)]
  SCR(windstorm,r)    = max(scenario A, scenario B) = 1.20 · L_r     — both A(80%+40%) and B(100%+20%) give 1.20·L gross  [Art.121(2-4)]
  SCR_windstorm       = sqrt( ΣΣ_(r,s) CorrWS(r,s) · SCR_r · SCR_s ) — regional aggregation                  [Art.121(1)]

APPROXIMATION (disclosed): the exact L_r weights each intra-country CRESTA zone by its Annex X risk weight W and
diversifies zones with the Annex XXII zone-correlation. We aggregate at COUNTRY level — one windstorm zone per
region, W = 1, perfect within-country correlation — so WSI_r = Σ sum insured in region r. Q and the inter-region
correlation are EXACT Annex V values; only the intra-country zone granularity is simplified. This tends to be
prudent on within-country diversification (it takes none) but does not apply the zonal risk weights, so it is an
APPROXIMATION of the exact zonal figure, not the exact figure. The zonal refinement (Annex IX/X/XXII) is future work.

Regions outside Annex V (Art.121(8-9), a premium-based charge using DIV and P_windstorm) are NOT computed here;
their exposure is reported separately as `other_regions` so it is disclosed, never silently dropped.
"""
from __future__ import annotations

import json
import math
import os
from functools import lru_cache

_PARAMS_PATH = os.path.join("data", "reference", "solvency2_windstorm_annex_v.json")
_GROSS_SCENARIO_FACTOR = 1.20   # Art.121(2-4): max(A: 0.8L+0.4L, B: 1.0L+0.2L) = 1.20·L gross of reinsurance


@lru_cache(maxsize=1)
def _params() -> dict | None:
    if not os.path.exists(_PARAMS_PATH):
        return None
    with open(_PARAMS_PATH) as f:
        return json.load(f)


def standard_formula_windstorm(policies: list[dict]) -> dict:
    """policies: the insurance book, each with `sum_insured_eur` and `country` (ISO-2). Returns the prescribed
    Solvency II standard-formula windstorm catastrophe SCR (gross of reinsurance), the per-region breakdown, the
    regional diversification benefit, the exact citation, and the disclosed approximation. Honest when it cannot
    run: returns available=False with a reason rather than a fabricated number."""
    p = _params()
    if not p or not p.get("verified"):
        return {"available": False, "reason": "official Annex V windstorm factors not loaded/verified",
                "citation": "Del. Reg. (EU) 2015/35, Art. 121 + Annex V"}

    order: list[str] = p["region_order"]
    idx = {r: i for i, r in enumerate(order)}
    iso2region: dict[str, str] = p["iso2_to_region"]
    regions_meta: dict[str, dict] = p["regions"]

    # sum insured by windstorm region (country ISO-2 -> region); non-listed countries tracked separately
    si_by_region: dict[str, float] = {}
    other_si = 0.0
    n_by_region: dict[str, int] = {}
    for pol in policies:
        si = pol.get("sum_insured_eur") or 0
        if si <= 0:
            continue
        cc = str(pol.get("country") or "").strip().upper()
        reg = iso2region.get(cc)
        if reg is None:
            other_si += si
            continue
        si_by_region[reg] = si_by_region.get(reg, 0.0) + si
        n_by_region[reg] = n_by_region.get(reg, 0) + 1

    if not si_by_region:
        return {"available": False, "reason": "no sum insured located in an Annex V windstorm region",
                "other_regions_sum_insured_eur": round(other_si),
                "citation": "Del. Reg. (EU) 2015/35, Art. 121 + Annex V"}

    # per-region specified loss and SCR  (Art.121(2),(5))
    per_region = []
    scr_r: dict[str, float] = {}
    for reg, si in sorted(si_by_region.items(), key=lambda kv: -kv[1]):
        q = regions_meta[reg]["q"]
        loss = q * si                       # L_r = Q_r · WSI_r  (WSI_r = SI_r under the country-level approximation)
        scr = _GROSS_SCENARIO_FACTOR * loss  # SCR_r = 1.20 · L_r
        scr_r[reg] = scr
        per_region.append({
            "region": reg, "region_name": regions_meta[reg]["name"],
            "sum_insured_eur": round(si), "n_policies": n_by_region[reg],
            "windstorm_factor_q": q, "specified_loss_eur": round(loss),
            "scr_windstorm_region_eur": round(scr),
        })

    # regional aggregation  SCR = sqrt( ΣΣ CorrWS(r,s)·SCR_r·SCR_s )   (Art.121(1))
    corr: dict[str, list[float]] = p["correlation"]
    var = 0.0
    for r, sr in scr_r.items():
        row = corr[r]
        for s, ss in scr_r.items():
            var += row[idx[s]] * sr * ss
    scr_windstorm = math.sqrt(var) if var > 0 else 0.0

    undiversified = sum(scr_r.values())   # Σ SCR_r (perfect correlation) — for the diversification benefit
    return {
        "available": True,
        "basis": "solvency_ii_standard_formula",
        "gross_of_reinsurance": True,
        "scr_windstorm_eur": round(scr_windstorm),
        "undiversified_scr_eur": round(undiversified),
        "regional_diversification_benefit_eur": round(undiversified - scr_windstorm),
        "per_region": per_region,
        "n_regions": len(per_region),
        "other_regions_sum_insured_eur": round(other_si),
        "scenario_gross_factor": _GROSS_SCENARIO_FACTOR,
        "citation": p.get("_citation", "Del. Reg. (EU) 2015/35, Art. 121 + Annex V"),
        "source": p.get("_source"),
        "params_version": p.get("_version"),
        "approximation": ("Country-level: one windstorm zone per region, risk weight W=1, perfect within-country "
                          "correlation (WSI_r = Σ sum insured in region r). Q(windstorm,r) and the inter-region "
                          "correlation are the EXACT Annex V values; the intra-country Annex IX/X/XXII zone "
                          "risk-weights and zone-diversification are not applied. Approximation, not the exact "
                          "zonal figure; gross of reinsurance."),
        "method": ("SCR_windstorm = sqrt(ΣΣ CorrWS(r,s)·SCR_r·SCR_s), SCR_r = 1.20·Q_r·SI_r "
                   "(Art.121(1),(2),(5); scenarios A and B both give 1.20·L gross)."),
    }
