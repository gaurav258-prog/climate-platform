"""Physical climate expected loss (€) of a banking book, on the bank's own stated method (E69).

    annual EL   = EAD × P(damaging event this year) × damage ratio
                = outstanding loan balance × method.annual_event_probability × method.damage_ratio

both read for the loan's headline peril at the band of its score (ml.scoring.damage_function; the bank's statement
per financial year, attested — services.money.params). LIFETIME EL sums the annual EL over the loan's remaining life,
year by year at the score interpolated between the engine's projection horizons, so risk past maturity is excluded.

A physical collateral-impairment expectation, NOT a Basel / IFRS 9 credit ECL (no PD). Undiscounted. A loan whose
maturity is not on the loan tape has no lifetime EL (a named gap, never a default tenor); a peril / band whose method
is not stated makes the loan's EL a gap, and the book's total a gap while any loan's is.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from ml.scoring.damage_function import damage_ratio, event_probability
from services.intelligence.horizon import NOW_YEAR, label_year, lerp

EL_VERSION = "el-v2.0-stated"
MID_YEAR = 0.5            # each year of a loan's life is read at its middle
BPS = 1e4                 # basis points per unit


def annual_expected_loss(method, ead: Optional[float], score: Optional[float], hazard: Optional[str]) -> dict:
    """EAD × P(event) × damage ratio, with its components; None components (and EL) where not stated."""
    if not ead or score is None:
        return {"annual_el_eur": 0.0, "p_event": None, "damage_ratio": None}
    p, dr = event_probability(method, hazard, score), damage_ratio(method, hazard, score)
    return {"annual_el_eur": None if p is None or dr is None else round(ead * p * dr, 2), "p_event": p, "damage_ratio": dr}


def score_at_year(year_offset: float, nodes: dict) -> Optional[float]:
    """The score at NOW+year_offset, linearly interpolated from the entity's per-horizon nodes
    {calendar_year: score}; flat before the first / after the last modelled node."""
    if not nodes:
        return None
    target = NOW_YEAR + year_offset
    yrs = sorted(nodes)
    if target <= yrs[0]:
        return nodes[yrs[0]]
    if target >= yrs[-1]:
        return nodes[yrs[-1]]
    for a, b in zip(yrs, yrs[1:]):
        if a <= target <= b:
            return lerp(nodes[a], nodes[b], (target - a) / (b - a))
    return nodes[yrs[-1]]


def lifetime_expected_loss(method, ead: Optional[float], nodes: dict, tenor_years: Optional[float],
                           hazard: Optional[str]) -> Optional[float]:
    """The annual EL summed over the loan's remaining life (mid-year score each year); None when the maturity is not
    known or a year's method is not stated."""
    if not ead or not nodes:
        return 0.0
    if not tenor_years or tenor_years <= 0:
        return None
    total = 0.0
    for y in range(int(round(tenor_years))):
        sc = score_at_year(y + MID_YEAR, nodes)
        if sc is None:
            continue
        el = annual_expected_loss(method, ead, sc, hazard)["annual_el_eur"]
        if el is None:
            return None
        total += el
    return round(total, 2)


def bank_expected_loss(session, org_id: str, scenario: str, *, method) -> dict:
    """Portfolio climate expected loss for a banking book: per-loan annual EL (next 12 months) and lifetime EL over the
    loan's REMAINING life (maturity-matched), rolled up. EAD = outstanding loan balance; residual maturity from the loan
    tape (ext_banking). method: the bank's stated method for the financial year (services.money.params.Method)."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (e.entity_id, v.time_horizon)
               e.entity_id::text AS eid, e.entity_name,
               CAST(x.outstanding_loan_balance_eur AS FLOAT) AS ead,
               CAST(x.residual_maturity_years AS FLOAT)     AS tenor,
               v.time_horizon AS horz, v.hazard_type AS hazard, v.physical_risk_score AS sc
        FROM portfolio_entities e
        JOIN v_portfolio_entity_physical_risk v ON v.entity_id = e.entity_id
        LEFT JOIN ext_banking x ON x.entity_id = e.entity_id
        WHERE e.org_id = :o AND e.vertical = 'banking' AND v.headline_eligible
          AND ( (v.scenario = :scen AND v.time_horizon <> 'current')
                OR (v.scenario = 'baseline' AND v.time_horizon = 'current') )
        ORDER BY e.entity_id, v.time_horizon, v.physical_risk_score DESC
    """), {"o": org_id, "scen": scenario}).mappings().all()

    ent: dict = {}
    for r in rows:
        d = ent.setdefault(r["eid"], {"name": r["entity_name"], "ead": r["ead"] or 0.0, "tenor": r["tenor"],
                                      "nodes": {}, "haz": {}})
        d["nodes"][label_year(r["horz"])] = r["sc"]
        d["haz"][label_year(r["horz"])] = r["hazard"]

    assets, tot_ead, tot_annual, tot_life = [], 0.0, 0.0, 0.0
    annual_gap = life_gap = no_tenor = 0
    for eid, d in ent.items():
        ead = d["ead"]
        if not ead:
            continue
        now_haz = d["haz"].get(NOW_YEAR) or next(iter(d["haz"].values()), None)
        ann = annual_expected_loss(method, ead, d["nodes"].get(NOW_YEAR), now_haz)
        tenor = d["tenor"] if d["tenor"] and d["tenor"] > 0 else None
        life = lifetime_expected_loss(method, ead, d["nodes"], tenor, now_haz)
        tot_ead += ead
        annual_gap += ann["annual_el_eur"] is None
        life_gap += life is None
        no_tenor += tenor is None
        tot_annual += ann["annual_el_eur"] or 0.0
        tot_life += life or 0.0
        assets.append({
            "entity_id": eid, "entity_name": d["name"], "ead_eur": round(ead, 2),
            "annual_el_eur": ann["annual_el_eur"], "lifetime_el_eur": life,
            "p_event": ann["p_event"], "damage_ratio": ann["damage_ratio"],
            "tenor_years": None if tenor is None else round(tenor, 1), "hazard": now_haz,
            "el_pct_of_ead": round(100 * life / ead, 2) if life is not None and ead else None,
        })
    assets.sort(key=lambda a: -(a["lifetime_el_eur"] or 0))
    gaps = [g for g in (method.gap_text(),
                        f"residual maturity not on the loan tape for {no_tenor} loan(s) — no lifetime EL for them" if no_tenor else None) if g]
    annual = None if annual_gap else round(tot_annual, 2)
    lifetime = None if life_gap else round(tot_life, 2)
    return {
        "version": EL_VERSION, "scenario": scenario, "total_ead_eur": round(tot_ead, 2),
        "annual_el_eur": annual, "lifetime_el_eur": lifetime,
        "annual_el_bps": round(BPS * annual / tot_ead, 1) if annual is not None and tot_ead else None,
        "lifetime_el_bps": round(BPS * lifetime / tot_ead, 1) if lifetime is not None and tot_ead else None,
        "n_assets": len(assets), "maturity_missing": no_tenor, "assets": assets,
        **({"gap": "; ".join(gaps)} if gaps else {}),
        "basis": ("Physical climate expected loss = outstanding balance × the bank's stated annual probability of a "
                  "damaging event × its stated damage ratio, for the loan's headline peril at the band of its score "
                  "(method parameters, attested). Lifetime EL sums the annual EL over each loan's remaining life from "
                  "the loan tape. A collateral-impairment expectation, NOT a Basel / IFRS 9 credit ECL (no PD). "
                  "Undiscounted. " + EL_VERSION + "."),
    }
