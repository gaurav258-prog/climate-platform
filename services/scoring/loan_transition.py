"""Loan-book transition-risk overlay — financed emissions + a carbon-price transition expected-loss, to sit
beside the physical value-loss on the same loan book.

The physical engine tells a bank what warming does to its collateral. The TRANSITION engine tells it what the
shift to a low-carbon economy does to its counterparties: a carbon price raises their operating cost and
strands part of their asset base. Both are credit risk to the loan.

For each loan counterparty this reuses two already-built pieces:
  * `services.reference.emissions_estimation.estimate_emissions` — a NACE sector-intensity × revenue estimate
    of scope 1+2, used to FILL where the counterparty has not reported emissions (flagged as estimated, never
    presented as reported);
  * `ml.scoring.transition_risk.transition_score` — the NGFS carbon-price cost and the sector stranded-asset
    fraction, per scenario × horizon.
The transition EXPECTED-LOSS on a loan is the modelled stranded-asset fraction applied to the outstanding
exposure — a bounded, disclosed quantity (the same "relative tier, not fitted" standard as the physical
damage schedule), not a new fitted PD model. Financed emissions are the counterparty's scope 1+2 (reported or
estimated); a rigorous PCAF attribution additionally needs each counterparty's EVIC, which is customer-supplied
— stated, never fabricated.
"""
from __future__ import annotations

from collections import defaultdict

from ml.scoring.transition_risk import transition_score
from services.reference.emissions_estimation import estimate_emissions


def _section(nace_code: str | None) -> str:
    return (nace_code or "").strip()[:2] or "—"


def loan_transition_overlay(assets: list[dict], scenario: str, horizon: str) -> dict:
    """assets: the bank loan book (each with nace_code, revenue_eur, ghg1/2/3, outstanding_loan_balance_eur,
    value_eur). Returns the per-book transition rollup: financed emissions (reported + estimated-fill),
    transition expected-loss (Σ outstanding × stranded fraction), coverage, and the by-sector concentration."""
    total_outstanding = total_financed = total_transition_el = 0.0
    n_scored = n_estimated = 0
    scored_score_x_exposure = 0.0
    by_sector: dict = defaultdict(lambda: {"outstanding": 0.0, "financed_emissions": 0.0, "transition_el": 0.0, "n": 0})
    top = []

    for a in assets:
        nace = a.get("nace_code")
        revenue = a.get("revenue_eur")
        s1, s2, s3 = a.get("ghg1"), a.get("ghg2"), a.get("ghg3")
        emissions_source = "reported"
        # fill missing reported scope 1+2 with a NACE sector-intensity estimate (flagged)
        if s1 is None and s2 is None and nace and revenue:
            est = estimate_emissions(nace, revenue)
            if est:
                s1, s2, emissions_source = est["scope1_2_tco2e"], 0.0, "estimated"

        blk = transition_score(s1, s2, s3, revenue, nace, scenario, horizon)
        if not blk:
            continue
        outstanding = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        stranded_frac = (blk.get("stranded_asset_pct") or 0.0) / 100.0
        transition_el = outstanding * stranded_frac
        financed_em = (s1 or 0.0) + (s2 or 0.0)

        n_scored += 1
        if emissions_source == "estimated":
            n_estimated += 1
        total_outstanding += outstanding
        total_financed += financed_em
        total_transition_el += transition_el
        scored_score_x_exposure += blk["transition_risk_score"] * outstanding

        sec = _section(nace)
        b = by_sector[sec]
        b["outstanding"] += outstanding
        b["financed_emissions"] += financed_em
        b["transition_el"] += transition_el
        b["n"] += 1

        top.append({
            "asset_id": a.get("asset_id") or a.get("entity_id"),
            "name": a.get("asset_name") or a.get("entity_name"), "nace_code": nace,
            "transition_risk_score": blk["transition_risk_score"], "risk_bucket": blk["risk_bucket"],
            "stranded_asset_pct": blk["stranded_asset_pct"],
            "carbon_price_impact_eur": blk.get("carbon_price_impact_eur"),
            "outstanding_eur": round(outstanding), "transition_el_eur": round(transition_el),
            "financed_emissions_tco2e": round(financed_em), "emissions_source": emissions_source,
        })

    if not n_scored:
        return {"available": False, "reason": "no_transition_signal"}

    top.sort(key=lambda r: -r["transition_el_eur"])
    sectors = sorted(
        [{"nace_section": k, "outstanding_eur": round(v["outstanding"]),
          "financed_emissions_tco2e": round(v["financed_emissions"]),
          "transition_el_eur": round(v["transition_el"]), "n": v["n"]} for k, v in by_sector.items()],
        key=lambda r: -r["transition_el_eur"])

    return {
        "available": True,
        "scenario": scenario, "horizon": horizon,
        "n_scored": n_scored,
        "financed_emissions_tco2e": round(total_financed),
        "n_emissions_estimated": n_estimated,
        "emissions_reported_pct": round(100 * (n_scored - n_estimated) / n_scored, 1) if n_scored else 0,
        "transition_expected_loss_eur": round(total_transition_el),
        "transition_el_pct_of_outstanding": round(100 * total_transition_el / total_outstanding, 2) if total_outstanding else 0,
        "exposure_weighted_transition_score": round(scored_score_x_exposure / total_outstanding, 1) if total_outstanding else None,
        "by_sector": sectors[:12],
        "top_exposures": top[:8],
        "method": ("Financed emissions = counterparty scope 1+2, reported or NACE sector-intensity estimated "
                   "(flagged); a rigorous PCAF attribution additionally needs counterparty EVIC (customer-supplied). "
                   "Transition expected-loss = outstanding × modelled stranded-asset fraction (NGFS carbon price + "
                   "sector stranding tiers) — a disclosed relative tier, not a fitted PD model."),
    }
