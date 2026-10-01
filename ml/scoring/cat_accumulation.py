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

The frequency and per-policy scenario loss are the SAME quantities the pricing engine produces on the undertaking's
stated method (E69: its damage ratios and event probabilities — a policy whose inputs are not stated makes the whole
result a gap, never a book with that policy left out). What the simulation adds is its DEFINITION of dependence —
perfect within a (peril, region) zone, independent across zones, a zone's event rate being its most-exposed policy's
occurrence rate — stated with every result. It is not a fitted vendor catastrophe model, nor an approved internal model.

Common random numbers: every zone draws its simulated years from its own stream, seeded by the organisation and the
zone — not by the scenario or horizon — and a policy's draw is fixed by its id. So the same simulated years are
replayed under every scenario: a scenario comparison (the ORSA's 'below 2 °C' against 'well above 2 °C', today
against 2050) shows the change in climate, not Monte-Carlo noise, and a higher occurrence rate can only add losses.

Net of reinsurance: the quota share applies to every loss; the per-occurrence cat excess of loss recovers on each
zone event (one event per zone per simulated year), in the aggregate (AEP) as well as the largest-event (OEP) view.
Reinstatements are taken as unlimited and their premiums are not modelled — disclosed.
"""
from __future__ import annotations

from collections import defaultdict

RETURN_PERIODS = (10, 50, 100, 200, 250)      # the reported ladder; 200 = the 99.5 % one-year level (Directive 2009/138/EC Art. 101(3))
SIMULATED_YEARS = 30000                        # simulated years per run (a setting of the computation, seeded)
RECONCILE_TOLERANCE = 0.05                     # the simulated mean is checked to lie within 5 % of the sum of expected losses


def catastrophe_accumulation(policies: list[dict], org_id: str, scenario: str, horizon: str, *,
                             pml_return_period: int | None, n_years: int = SIMULATED_YEARS,
                             reinsurance: dict | None = None, zones_of: dict | None = None) -> dict:
    """policies: the priced insurance book (each with pricing.net_scenario_loss_eur /
    .annual_occurrence_prob / .expected_annual_loss_eur, plus headline_hazard and region). Returns the
    AEP/OEP exceedance losses, the PML, and the reconciliation of the simulated mean to the EAL sum.

    pml_return_period: the return period the PML is read at — an institution interpretation switch. Solvency II
    SCR is 1-in-200 (99.5% VaR); rating agencies commonly use 1-in-250. The chosen period is always included in
    the reported AEP/OEP curves so the ladder shows it. Not chosen (None) → the ladder is reported and the PML is a
    named gap (E69): the platform picks no return period.

    zones_of: {policy id: (peril, region)} — hold the accumulation zones fixed across a scenario comparison (taken from
    the reference book). Otherwise a policy's zone follows its headline hazard in THIS scenario, and a policy whose
    headline hazard changes between scenarios would regroup the zones — changing the tail for a reason that is not
    the climate."""
    # the reported return-period ladder always includes the chosen PML period
    return_periods = sorted(set(RETURN_PERIODS) | ({pml_return_period} if pml_return_period else set()))
    import hashlib

    import numpy as np

    # one component per insured peril of a policy (multi-peril pricing, ml.scoring.insurance_pricing.price_perils);
    # a policy priced on a single peril is one component of its headline hazard
    comps = []
    for p in policies:
        pr = p.get("pricing") or {}
        if pr and (pr.get("gap") or any(c.get("net_scenario_loss_eur") is None or c.get("annual_occurrence_prob") is None
                                        for c in (pr.get("perils") or []))):
            return {"available": False, "reason": "gap", "gap": pr.get("gap") or "a peril's damage ratio or event "
                                                                                   "probability is not stated"}
        pid = str(p.get("policy_id") or p.get("entity_id") or "")
        region = p.get("region") or "unspecified"
        if pr.get("perils") is not None:
            comps += [{"id": f"{pid}|{c['hazard']}", "zone": (c["hazard"], region),
                       "loss": c["net_scenario_loss_eur"], "prob": c["annual_occurrence_prob"],
                       "eal": c["expected_annual_loss_eur"]} for c in pr["perils"] if (c["net_scenario_loss_eur"] or 0) > 0]
        elif (pr.get("net_scenario_loss_eur") or 0) > 0:
            zone = (zones_of or {}).get(pid) or (p.get("headline_hazard") or "unknown", region)
            comps.append({"id": pid, "zone": tuple(zone), "loss": pr["net_scenario_loss_eur"],
                          "prob": pr["annual_occurrence_prob"], "eal": pr["expected_annual_loss_eur"]})
    if not comps:
        return {"available": False, "reason": "no_priced_policies"}

    # accumulation zones — one shared event per (peril, region)
    zones: dict = defaultdict(list)
    for c in comps:
        zones[c["zone"]].append(c)

    def stream(*key) -> np.random.Generator:
        """A stream fixed by the organisation and the key — never by the scenario or horizon (common random numbers),
        deterministic across processes and redeploys (audit T2)."""
        return np.random.default_rng(int.from_bytes(hashlib.sha256("|".join((str(org_id), "cat", *map(str, key))).encode())
                                                    .digest()[:8], "big"))

    qs = att = lim = None
    if reinsurance:
        qs = max(0.0, min(1.0, (reinsurance.get("quota_share_pct") or 0) / 100.0))
        att = reinsurance.get("xol_attachment_eur")
        lim = reinsurance.get("xol_limit_eur")

    def net_of(event_loss):
        """An event's loss after the quota share and the per-occurrence cat excess of loss."""
        net = event_loss * (1.0 - qs)
        if att is not None and lim:
            net = net - np.clip(net - float(att), 0.0, float(lim))
        return net

    annual = np.zeros(n_years)        # aggregate loss per simulated year (AEP)
    occ_max = np.zeros(n_years)       # largest single zone-event loss per year (OEP)
    net_annual = np.zeros(n_years)
    net_occ = np.zeros(n_years)
    sum_eal = sum(c["eal"] for c in comps)

    for zkey in sorted(zones):
        zpol = sorted(zones[zkey], key=lambda c: c["id"])
        losses = np.array([c["loss"] for c in zpol], dtype=float)
        probs = np.array([c["prob"] for c in zpol], dtype=float)
        losses = np.nan_to_num(losses, nan=0.0, posinf=0.0, neginf=0.0)   # never let a bad value blow up the tail
        q = float(probs.max())        # zone event rate = most-exposed policy's occurrence rate
        if q <= 0:
            continue
        cond = np.clip(probs / q, 0.0, 1.0)   # conditional realisation preserves each marginal EAL
        # the zone's years and each policy's draw come from streams fixed by the zone and the policy: the same
        # simulated years under every scenario (a higher rate fires in a superset of years)
        fired = stream(*zkey, "event").random(n_years) < q
        idx = np.nonzero(fired)[0]
        if idx.size == 0:
            continue
        u = np.column_stack([stream(*zkey, "policy", c["id"] or i).random(n_years)[idx] for i, c in enumerate(zpol)])
        # which policies are hit given the event × their loss. Element-wise multiply + row-sum rather than a
        # matmul, which raises spurious "divide by zero" RuntimeWarnings on some numpy/BLAS builds.
        realized = u < cond
        event_loss = (realized * losses).sum(axis=1)   # this zone's loss in each fired year
        annual[idx] += event_loss
        occ_max[idx] = np.maximum(occ_max[idx], event_loss)
        if reinsurance:
            ev_net = net_of(event_loss)
            net_annual[idx] += ev_net
            net_occ[idx] = np.maximum(net_occ[idx], ev_net)

    def rp(arr, t):   # 1-in-t-year loss = the (1 - 1/t) quantile
        return float(np.quantile(arr, 1.0 - 1.0 / t))

    mean_annual = float(annual.mean())
    out = {
        "available": True,
        "n_years": n_years,
        "n_zones": len(zones),
        "n_policies": len({c["id"].split("|")[0] for c in comps}),
        "n_peril_components": len(comps),
        "mean_annual_loss_eur": round(mean_annual),
        "sum_independent_eal_eur": round(sum_eal),
        # the simulated mean should sit within Monte-Carlo error of the independent EAL sum
        "mean_reconciles": bool(abs(mean_annual - sum_eal) <= RECONCILE_TOLERANCE * sum_eal) if sum_eal else True,
        "aep_eur": {f"rp_{t}": round(rp(annual, t)) for t in return_periods},
        "oep_eur": {f"rp_{t}": round(rp(occ_max, t)) for t in return_periods},
        "pml_eur": round(rp(occ_max, pml_return_period)) if pml_return_period else None,
        "pml_return_period": pml_return_period,
        "tail_to_mean_multiple": (round(rp(annual, pml_return_period) / mean_annual, 1)
                                  if mean_annual and pml_return_period else None),
        **({} if pml_return_period else {"pml_gap": "not stated: the PML return period (calculation settings — pml_return_period)"}),
        "method": ("common-shock Monte-Carlo on the undertaking's stated damage ratios and event probabilities: a "
                   "(peril, region) zone event fires at the zone's occurrence rate; policies realise their scenario loss "
                   "conditional on that shared event, preserving each policy's marginal expected loss. Dependence by "
                   "definition: perfect within a zone, independent across zones. Not a fitted vendor catastrophe model, "
                   "nor an approved internal model."),
    }

    # ── Net of reinsurance ── every zone event netted as it occurs (above): the quota share on every loss, the
    # per-occurrence cat XoL on each event, in the aggregate as well as the largest-event view.
    if reinsurance:
        gross_pml = out["pml_eur"]
        net_pml = round(rp(net_occ, pml_return_period)) if pml_return_period else None
        out["net_of_reinsurance"] = {
            "quota_share_pct": round(qs * 100, 1),
            "xol_attachment_eur": round(att) if att is not None else None,
            "xol_limit_eur": round(lim) if lim else None,
            "net_aep_eur": {f"rp_{t}": round(rp(net_annual, t)) for t in return_periods},
            "net_oep_eur": {f"rp_{t}": round(rp(net_occ, t)) for t in return_periods},
            "net_pml_eur": net_pml,
            "net_mean_annual_loss_eur": round(float(net_annual.mean())),
            "ceded_pml_eur": round(gross_pml - net_pml) if gross_pml is not None and net_pml is not None else None,
            "cession_ratio_pct": round(100 * (1 - net_pml / gross_pml), 1) if gross_pml and net_pml is not None else None,
            "note": ("Net = gross after ceding, event by event: the quota share on every loss, the per-occurrence "
                     "cat excess of loss on each zone event (aggregate and largest-event views). Reinstatements are "
                     "taken as unlimited; their premiums and any aggregate treaty are not modelled."),
        }
    return out
