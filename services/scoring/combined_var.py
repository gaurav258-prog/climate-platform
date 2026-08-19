"""Combined physical + transition climate VaR — one probabilistic loss distribution over BOTH climate
drivers, for an asset-manager's book.

The portfolio VaR was physical-haircut only: it modelled what warming does to a holding's value, but not
what the low-carbon transition does to it. Both hit the SAME position. This runs one Monte-Carlo per holding
over the two drivers:
  * physical — the continuous collateral haircut on the holding's headline physical score, sampled around its
    own per-cell confidence interval (falling back to a relative spread where no CI exists);
  * transition — the modelled stranded-asset fraction for the holding's sector under the scenario's NGFS
    carbon-price path (ml.scoring.transition_risk; the sector-stranding channel, which needs only the NACE
    code — the carbon-cost channel additionally needs issuer emissions and is out of scope for the flat book).
A holding is not lost twice: the two are combined as complementary survival — loss = 1 − (1−physical)(1−transition)
— so the combined figure never exceeds the position and is always ≤ the naive sum of the two. Returns the
combined VaR (median / P95 / P99) plus the physical-only and transition-only expected components, so the
decomposition is visible. Deterministic seed (audit T2). Disclosed relative tiers, not a fitted model.
"""
from __future__ import annotations

_DEFAULT_SIMS = 10000


def combined_climate_var(holdings: list[dict], org_id: str, scenario: str, horizon: str,
                         n_sims: int = _DEFAULT_SIMS) -> dict:
    """holdings: the asset-manager book (each with position_value_eur, headline_score/bucket/hazard, hazards
    with ci_lo/ci_hi, nace_code). Returns the combined physical+transition climate VaR with decomposition."""
    import hashlib

    import numpy as np

    from ml.scoring.damage_function import collateral_haircut_pct
    from ml.scoring.transition_risk import transition_score

    priced = [h for h in holdings if (h.get("position_value_eur") or 0) > 0 and h.get("headline_bucket")]
    if not priced:
        return {"available": False, "reason": "no_scored_positions"}

    seed = int.from_bytes(hashlib.sha256(f"{org_id}|{scenario}|{horizon}|combined".encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)

    losses = np.zeros(n_sims)
    phys_expected = trans_expected = combined_expected = 0.0
    total_value = 0.0
    n_transition = 0

    for h in priced:
        value = h["position_value_eur"] or 0.0
        total_value += value
        score, bucket, hazard = h.get("headline_score"), h.get("headline_bucket"), h.get("headline_hazard")
        phys = collateral_haircut_pct(score, bucket, hazard) / 100.0

        tblk = transition_score(None, None, None, None, h.get("nace_code"), scenario, horizon)
        trans = (tblk["stranded_asset_pct"] or 0.0) / 100.0 if tblk else 0.0
        if tblk:
            n_transition += 1

        phys_expected += value * phys
        trans_expected += value * trans
        combined_mean = 1.0 - (1.0 - phys) * (1.0 - trans)
        combined_expected += value * combined_mean

        # physical draw around the per-cell CI band (or a relative spread if no CI)
        ci = next((x for x in (h.get("hazards") or []) if x.get("hazard") == hazard), None)
        if ci and ci.get("ci_lo") is not None and ci.get("ci_hi") is not None:
            plo = collateral_haircut_pct(ci["ci_lo"], bucket, hazard) / 100.0
            phi = collateral_haircut_pct(ci["ci_hi"], bucket, hazard) / 100.0
        else:
            spread = max(phys * 0.4, 0.02)
            plo, phi = max(0.0, phys - spread), min(1.0, phys + spread)
        pdraw = (rng.triangular(min(plo, phi), phys, max(plo, phi), n_sims)
                 if phi > plo else np.full(n_sims, phys))

        # transition draw around a relative spread (the stranding tier is a disclosed relative estimate)
        if trans > 0:
            tspread = max(trans * 0.5, 0.01)
            tlo, thi = max(0.0, trans - tspread), min(1.0, trans + tspread)
            tdraw = rng.triangular(tlo, trans, thi, n_sims) if thi > tlo else np.full(n_sims, trans)
        else:
            tdraw = np.zeros(n_sims)

        losses += value * (1.0 - (1.0 - pdraw) * (1.0 - tdraw))

    p50, p95, p99 = (float(x) for x in np.percentile(losses, [50, 95, 99]))
    return {
        "available": True,
        "scenario": scenario, "horizon": horizon,
        "n_positions": len(priced), "n_with_transition": n_transition, "n_sims": n_sims,
        "median_loss_eur": round(p50),
        "var95_eur": round(p95),
        "var99_eur": round(p99),
        "physical_expected_eur": round(phys_expected),
        "transition_expected_eur": round(trans_expected),
        "combined_expected_eur": round(combined_expected),
        "combined_pct_of_book": round(100 * combined_expected / total_value, 2) if total_value else 0,
        "method": ("one Monte-Carlo per holding over both drivers — physical (continuous haircut, sampled "
                   "around the per-cell confidence interval) and transition (sector stranded-asset fraction "
                   "under the scenario's NGFS carbon price). Combined as 1−(1−physical)(1−transition), so a "
                   "holding is never lost twice. Disclosed relative tiers, not a fitted model."),
    }
