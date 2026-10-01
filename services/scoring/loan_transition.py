"""Loan-book transition-risk overlay — financed emissions and a transition expected loss on the institution's stated
method, beside the physical value-loss on the same loan book.

For each loan counterparty:
  * scope 1+2 emissions — reported, or FILLED with the EXIOBASE sector-intensity estimate
    (services.reference.emissions_estimation; flagged as estimated, never presented as reported);
  * ml.scoring.transition_risk.transition_block — the stated carbon price and the stated stranded share of the
    counterparty's NACE division under the scenario and horizon.
The transition EXPECTED LOSS on a loan is its outstanding balance × the stated stranded share. The outstanding balance is
the exposure; a loan without one is a gap, never replaced by the collateral value. A gap in any loan makes the book
total a gap, never a partial sum. Financed emissions here are gross scope 1+2 (the PCAF-attributed figure is the KRI's).
"""
from __future__ import annotations

from collections import defaultdict

from ml.scoring.epc_stranding import bank_collateral_stranding_rollup, loan_collateral_stranding
from ml.scoring.transition_risk import transition_block
from services.reference.emissions_estimation import estimate_emissions

# Loans whose CREDIT is secured on a building (the collateral an energy-performance discount bites on). Corporate loans
# to operating companies carry their transition risk on the COUNTERPARTY (the carbon-price / stranding overlay).
_RE_COLLATERAL_TYPES = {"residential_real_estate", "commercial_real_estate", "office"}


def collateral_stranding_overlay(method, assets: list[dict]) -> dict:
    """The bank's transition risk ON ITS REAL-ESTATE COLLATERAL, on the stated brown discount per EPC grade. `assets`
    are bank loan rows (asset_type, epc_label, value_eur = collateral value, outstanding_loan_balance_eur)."""
    re_assets = [a for a in assets if (a.get("asset_type") or a.get("entity_type")) in _RE_COLLATERAL_TYPES]
    if not re_assets:
        return {"available": False, "reason": "no_real_estate_collateral"}
    roll = bank_collateral_stranding_rollup(method, [
        {"epc_label": a.get("epc_label"), "asset_value_eur": a.get("value_eur"),
         "outstanding_loan_balance_eur": a.get("outstanding_loan_balance_eur")} for a in re_assets])
    if roll.get("gap"):
        return {"available": True, **roll}
    top = []
    for a in re_assets:
        r = loan_collateral_stranding(method, a.get("epc_label"), a.get("value_eur"), a.get("outstanding_loan_balance_eur"))
        if r["assessed"] and r["discounted"]:
            top.append({"asset_id": a.get("asset_id") or a.get("entity_id"), "name": a.get("asset_name") or a.get("entity_name"),
                        "asset_type": a.get("asset_type") or a.get("entity_type"), "epc_rating": r["epc_rating"],
                        "brown_discount_pct": r["brown_discount_pct"], "original_ltv_pct": r["original_ltv_pct"],
                        "stressed_ltv_pct": r["stressed_ltv_pct"],
                        "collateral_value_at_risk_eur": r["collateral_value_at_risk_eur"],
                        "loan_value_at_risk_eur": r["loan_value_at_risk_eur"], "retrofit_capex_eur": r["retrofit_capex_eur"]})
    top.sort(key=lambda r: -r["loan_value_at_risk_eur"])
    return {"available": True, **roll, "top_exposures": top[:8]}


def _division(nace_code: str | None) -> str | None:
    """The NACE division of the counterparty ('C24'), from the platform's NACE reference; None if unclassified."""
    from services.reference import nace
    return nace.division(nace_code)


def _label(division: str | None) -> str:
    from services.reference import nace
    return (nace.label(division) if division else None) or "Unclassified"


def loan_transition_overlay(method, assets: list[dict], scenario: str, horizon: str, eur_per_unit: float = 1.0) -> dict:
    """assets: the bank loan book (nace_code, revenue_eur, ghg1/2/3, outstanding_loan_balance_eur), amounts in the book's
    currency; eur_per_unit converts that currency to EUR (the unit of the sector intensities and the stated carbon
    price). Returns financed emissions (reported + estimated fill), the transition expected loss (Σ outstanding × stated
    stranded share), the exposure-weighted transition score, and the by-division concentration — or the gaps."""
    by_sector: dict = defaultdict(lambda: {"outstanding": 0.0, "financed_emissions": None, "transition_el": 0.0, "n": 0})
    rows, gaps, no_outstanding = [], set(), 0
    for a in assets:
        nace, revenue = a.get("nace_code"), a.get("revenue_eur")
        s1, s2 = a.get("ghg1"), a.get("ghg2")
        source = "reported"
        if s1 is None and s2 is None and nace and revenue:
            est = estimate_emissions(nace, revenue * eur_per_unit)
            if est:
                s1, s2, source = est["scope1_2_tco2e"], 0.0, "estimated"
        div = _division(nace)
        blk = transition_block(method, s1, s2, revenue, div, scenario, horizon, eur_per_unit)
        if blk.get("gap"):
            gaps.add(blk["gap"].removeprefix("not stated: "))
        outstanding = a.get("outstanding_loan_balance_eur")
        if not outstanding:
            no_outstanding += 1
        rows.append((a, blk, div, outstanding, source, s1, s2))

    base = {"scenario": scenario, "horizon": horizon, "n_loans": len(rows)}
    if not rows:
        return {"available": False, "reason": "no_loans"}
    if gaps or no_outstanding:
        parts = ([f"not stated: {', '.join(sorted(gaps))}"] if gaps else []) + \
                ([f"{no_outstanding} loan(s) have no outstanding balance on record"] if no_outstanding else [])
        return {"available": True, **base, "gap": "; ".join(parts)}

    total_out = total_fin = total_el = 0.0
    scored_out = scored_x = 0.0
    n_est = 0
    top = []
    for a, blk, div, outstanding, source, s1, s2 in rows:
        el = outstanding * blk["stranded_asset_pct"] / 100
        # the scopes the counterparty states (or the sector estimate of scope 1+2); a missing scope is not 0 (E76)
        stated = [v for v in (s1, s2) if v is not None]
        fin = sum(stated) if stated and blk["has_emissions"] else None
        total_out += outstanding
        total_el += el
        if fin is not None:
            total_fin += fin
            n_est += source == "estimated"
        if blk["transition_risk_score"] is not None:
            scored_out += outstanding
            scored_x += blk["transition_risk_score"] * outstanding
        b = by_sector[div]
        b["outstanding"] += outstanding
        if fin is not None:
            b["financed_emissions"] = (b["financed_emissions"] or 0.0) + fin
        b["transition_el"] += el
        b["n"] += 1
        top.append({"asset_id": a.get("asset_id") or a.get("entity_id"), "name": a.get("asset_name") or a.get("entity_name"),
                    "nace_code": a.get("nace_code"), "transition_risk_score": blk["transition_risk_score"],
                    "risk_bucket": blk["risk_bucket"], "stranded_asset_pct": blk["stranded_asset_pct"],
                    "carbon_price_impact": blk["carbon_price_impact"], "outstanding_eur": round(outstanding),
                    "transition_el_eur": round(el), "financed_emissions_tco2e": round(fin) if fin is not None else None,
                    "emissions_source": source if fin is not None else None})
    n_em = sum(1 for _, blk, *_ in rows if blk["has_emissions"])
    top.sort(key=lambda r: -r["transition_el_eur"])
    sectors = sorted(
        [{"nace_division": k or "—", "label": _label(k), "outstanding_eur": round(v["outstanding"]),
          "financed_emissions_tco2e": None if v["financed_emissions"] is None else round(v["financed_emissions"]), "transition_el_eur": round(v["transition_el"]), "n": v["n"]}
         for k, v in by_sector.items()], key=lambda r: -r["transition_el_eur"])
    return {
        "available": True, **base,
        "financed_emissions_tco2e": round(total_fin),
        "n_with_emissions": n_em, "n_emissions_estimated": n_est,
        "emissions_reported_pct": round(100 * (n_em - n_est) / n_em, 1) if n_em else None,
        "transition_expected_loss_eur": round(total_el),
        "transition_el_pct_of_outstanding": round(100 * total_el / total_out, 2) if total_out else None,
        "exposure_weighted_transition_score": round(scored_x / scored_out, 1) if scored_out else None,
        "score_coverage_pct": round(100 * scored_out / total_out, 1) if total_out else None,
        "by_sector": sectors[:12],
        "top_exposures": top[:8],
        "method": ("Financed emissions = counterparty gross scope 1+2 (reported, or the EXIOBASE sector-intensity "
                   "estimate, flagged) — not PCAF-attributed (see the Financed-emissions KRI for that). Transition "
                   "expected loss = outstanding × the institution's stated stranded share for the counterparty's NACE "
                   "division under the scenario and horizon; the carbon cost uses its stated carbon price."),
    }
