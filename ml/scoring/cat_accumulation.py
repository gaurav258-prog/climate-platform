"""Portfolio catastrophe accumulation — AEP / OEP exceedance curves & PML.

A property insurer holds capital against the TAIL of correlated catastrophe losses, not the sum of
independent per-policy expected annual losses (EAL). One windstorm or flood hits every policy in its
footprint at once; summing independent EALs hides that accumulation and understates the 1-in-100/250 year.

This is a common-shock Monte-Carlo over regional peril "zones" — (peril, region). In each simulated year a
zone's event fires at the zone's occurrence rate; the policies in that zone then realise their modelled
scenario loss CONDITIONAL on that shared event. That conditioning preserves each policy's own marginal EAL
(so the simulated mean reconciles to the independent EAL sum — the honesty check) while making the losses in
a zone move together, which is what fattens the tail. From the simulated distribution we read the aggregate
(AEP) and single-occurrence (OEP) exceedance losses and the probable maximum loss (PML = 1-in-250 OEP).

Honest by construction: the frequency and per-policy scenario loss are the SAME quantities the pricing
engine already produces. The only added assumptions are the correlation structure — perfect within a
(peril, region) zone, independent across zones — and that a zone's event rate is its most-exposed policy's
occurrence rate. Both are disclosed. This is NOT a fitted vendor catastrophe model.
"""
from __future__ import annotations

from collections import defaultdict

_BASE_RETURN_PERIODS = [10, 50, 100, 250]
_DEFAULT_PML_RETURN_PERIOD = 250
_DEFAULT_SIMS = 30000


def catastrophe_accumulation(policies: list[dict], org_id: str, scenario: str, horizon: str,
                             n_years: int = _DEFAULT_SIMS,
                             pml_return_period: int = _DEFAULT_PML_RETURN_PERIOD) -> dict:
    """policies: the priced insurance book (each with pricing.net_scenario_loss_eur /
    .annual_occurrence_prob / .expected_annual_loss_eur, plus headline_hazard and region). Returns the
    AEP/OEP exceedance losses, the PML, and the reconciliation of the simulated mean to the EAL sum.

    pml_return_period: the return period the PML is read at — an institution interpretation switch. Solvency II
    SCR is 1-in-200 (99.5% VaR); rating agencies commonly use 1-in-250. The chosen period is always included in
    the reported AEP/OEP curves so the ladder shows it."""
    # the reported return-period ladder always includes the chosen PML period
    return_periods = sorted(set(_BASE_RETURN_PERIODS) | {pml_return_period})
    import hashlib

    import numpy as np

    priced = [p for p in policies
              if p.get("pricing") and (p["pricing"].get("net_scenario_loss_eur") or 0) > 0]
    if not priced:
        return {"available": False, "reason": "no_priced_policies"}

    # accumulation zones — one shared event per (peril, region)
    zones: dict = defaultdict(list)
    for p in priced:
        zones[(p.get("headline_hazard") or "unknown", p.get("region") or "unspecified")].append(p)

    # deterministic across processes/redeploys (same pattern as monte_carlo_var, audit T2)
    seed = int.from_bytes(hashlib.sha256(f"{org_id}|{scenario}|{horizon}|cat".encode()).digest()[:8], "big")
    rng = np.random.default_rng(seed)

    annual = np.zeros(n_years)        # aggregate loss per simulated year (AEP)
    occ_max = np.zeros(n_years)       # largest single zone-event loss per year (OEP)
    sum_eal = sum(p["pricing"]["expected_annual_loss_eur"] for p in priced)

    for zpol in zones.values():
        losses = np.array([p["pricing"]["net_scenario_loss_eur"] for p in zpol], dtype=float)
        probs = np.array([p["pricing"]["annual_occurrence_prob"] for p in zpol], dtype=float)
        losses = np.nan_to_num(losses, nan=0.0, posinf=0.0, neginf=0.0)   # never let a bad value blow up the tail
        q = float(probs.max())        # zone event rate = most-exposed policy's occurrence rate
        if q <= 0:
            continue
        cond = np.clip(probs / q, 0.0, 1.0)   # conditional realisation preserves each marginal EAL
        fired = rng.random(n_years) < q       # does the zone's event occur this year?
        idx = np.nonzero(fired)[0]
        if idx.size == 0:
            continue
        # which policies are hit given the event × their loss. Element-wise multiply + row-sum rather than a
        # matmul, which raises spurious "divide by zero" RuntimeWarnings on some numpy/BLAS builds.
        realized = rng.random((idx.size, len(zpol))) < cond
        event_loss = (realized * losses).sum(axis=1)   # this zone's loss in each fired year
        annual[idx] += event_loss
        occ_max[idx] = np.maximum(occ_max[idx], event_loss)

    def rp(arr, t):   # 1-in-t-year loss = the (1 - 1/t) quantile
        return float(np.quantile(arr, 1.0 - 1.0 / t))

    mean_annual = float(annual.mean())
    return {
        "available": True,
        "n_years": n_years,
        "n_zones": len(zones),
        "n_policies": len(priced),
        "mean_annual_loss_eur": round(mean_annual),
        "sum_independent_eal_eur": round(sum_eal),
        # the simulated mean should sit within Monte-Carlo error of the independent EAL sum
        "mean_reconciles": bool(abs(mean_annual - sum_eal) <= 0.05 * sum_eal) if sum_eal else True,
        "aep_eur": {f"rp_{t}": round(rp(annual, t)) for t in return_periods},
        "oep_eur": {f"rp_{t}": round(rp(occ_max, t)) for t in return_periods},
        "pml_eur": round(rp(occ_max, pml_return_period)),
        "pml_return_period": pml_return_period,
        "tail_to_mean_multiple": round(rp(annual, pml_return_period) / mean_annual, 1) if mean_annual else None,
        "method": ("common-shock Monte-Carlo: a (peril, region) zone event fires at the zone's occurrence "
                   "rate; policies realise their scenario loss conditional on that shared event, preserving "
                   "each policy's marginal EAL. Correlation perfect within a zone, independent across zones. "
                   "Not a fitted vendor cat model."),
    }
