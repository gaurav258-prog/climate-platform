"""Combined physical + transition climate VaR — one loss distribution over both climate drivers for an asset
manager's book, on the manager's own stated method (E69).

Per holding, one Monte-Carlo over:
  * physical   — its discount for physical risk (its override, else the stated valuation haircut for its headline peril
                 and band), sampled between the discounts at the ends of its score's confidence interval, or, without
                 one, within ± the stated relative uncertainty (method.var_relative_uncertainty);
  * transition — the stated stranded share for its NACE division under the scenario and horizon
                 (method.stranded_share), sampled within ± the stated relative uncertainty
                 (method.transition_var_relative_uncertainty).
Combined per the manager's dependence switch (independent 1−(1−p)(1−t) / additive / max), so a holding is never lost
more than once. Deterministic seed (audit T2). A gap — never a partial figure — when an input is not stated.
"""
from __future__ import annotations

from ml.scoring.valuation_discount import VAR_QUANTILES, effective_haircut


def _combine(physical, transition, dependence: str):
    """'independent' = 1−(1−p)(1−t); 'additive' = min(1, p+t); 'max' = the larger — an institution switch."""
    import numpy as np
    if dependence == "additive":
        return np.minimum(1.0, np.add(physical, transition))
    if dependence == "max":
        return np.maximum(physical, transition)
    return 1.0 - (1.0 - np.asarray(physical)) * (1.0 - np.asarray(transition))


def _band(rng, mean: float, lo: float, hi: float, n: int):
    import numpy as np
    return rng.triangular(lo, mean, hi, n) if hi > lo else np.full(n, mean)


def combined_climate_var(method, holdings: list[dict], org_id: str, scenario: str, horizon: str, n_sims: int,
                         dependence: str | None) -> dict:
    """holdings: the book (position_value_eur, headline_score/hazard, hazards with ci_lo/ci_hi, nace_code, valuation)."""
    import hashlib

    import numpy as np

    from ml.scoring.damage_function import valuation_haircut
    from services.reference.nace import division

    priced = [h for h in holdings if (h.get("position_value_eur") or 0) > 0 and h.get("headline_score") is not None]
    if not priced:
        return {"available": False, "reason": "no_scored_positions"}
    if dependence is None:          # the manager's own choice of how physical and transition losses combine (E69)
        return {"available": False, "reason": "gap",
                "gap": "not stated: the physical × transition dependence (calculation settings — climate_var_dependence)"}
    rel_p, rel_t = method.get("method.var_relative_uncertainty"), method.get("method.transition_var_relative_uncertainty")
    rows = []
    for h in priced:
        phys = effective_haircut(method, h)
        trans = method.per_division("method.stranded_share", division(h.get("nace_code")) or "any", scenario, horizon)
        ci = next((x for x in (h.get("hazards") or []) if x.get("hazard") == h.get("headline_hazard")), None)
        ends = None
        if ci and ci.get("ci_lo") is not None and ci.get("ci_hi") is not None and not (h.get("valuation") or {}).get("is_overridden"):
            ends = (valuation_haircut(method, h["headline_hazard"], ci["ci_lo"]),
                    valuation_haircut(method, h["headline_hazard"], ci["ci_hi"]))
        rows.append((h, phys, trans, ends))
    if rel_p is None or rel_t is None or any(p is None or t is None or (e and None in e) for _, p, t, e in rows):
        return {"available": False, "reason": "gap", "gap": method.gap_text()}

    seed = int.from_bytes(hashlib.sha256(f"{org_id}|{scenario}|{horizon}|combined".encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    losses = np.zeros(n_sims)
    phys_exp = trans_exp = comb_exp = total = 0.0
    for h, phys, trans, ends in rows:
        value = h["position_value_eur"]
        total += value
        phys_exp += value * phys
        trans_exp += value * trans
        comb_exp += value * float(_combine(phys, trans, dependence))
        plo, phi = (min(ends), max(ends)) if ends else (max(0.0, phys * (1 - rel_p)), min(1.0, phys * (1 + rel_p)))
        pdraw = _band(rng, phys, plo, phi, n_sims)
        tdraw = _band(rng, trans, max(0.0, trans * (1 - rel_t)), min(1.0, trans * (1 + rel_t)), n_sims)
        losses += value * _combine(pdraw, tdraw, dependence)
    p50, p95, p99 = (float(x) for x in np.percentile(losses, VAR_QUANTILES))
    return {
        "available": True, "scenario": scenario, "horizon": horizon, "n_positions": len(rows), "n_sims": n_sims,
        "dependence": dependence, "median_loss_eur": round(p50), "var95_eur": round(p95), "var99_eur": round(p99),
        "physical_expected_eur": round(phys_exp), "transition_expected_eur": round(trans_exp),
        "combined_expected_eur": round(comb_exp),
        "combined_pct_of_book": round(100 * comb_exp / total, 2) if total else None,
        "method": ("one Monte-Carlo per holding over both drivers on the manager's stated method: physical (its discount, "
                   "sampled across its score's confidence interval or its stated uncertainty) and transition (its stated "
                   "stranded share for the division, scenario and horizon, sampled within its stated uncertainty); "
                   f"combined as '{dependence}'."),
    }
