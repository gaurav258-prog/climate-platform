"""Near-term climate EXPECTED LOSS (€) — the number a credit officer actually acts on.

Turns the 0–100 physical-risk score into money via the textbook expected-loss identity, using
ONLY functions the platform already discloses — no borrowed / invented PD·LGD:

    annual EL = EAD × P(event this year) × mean damage-ratio
              = exposure × annual_loss_probability(score)      ← insurance loss curve (disclosed)
                         × mean_damage_ratio(score, attrs)      ← CLIMADA/Emanuel damage function (df-v1.0)

  • P(event this year)  = annual_loss_probability(score)  — the frequency piece (answers "will something
                          hit this exposure in a given year"), the near-term quantity the score alone hides.
  • mean damage-ratio   = the severity piece (fraction of value lost if it does hit), vulnerability-adjusted.
  • EAD                 = outstanding loan balance (exposure at default).

LIFETIME EL (maturity-matched): accumulate the annual EL year by year over the loan's REMAINING life, with
the physical-risk score evolving between the engine's modelled horizon nodes (interpolated per year, exactly
like the horizon picker). A 3-year loan therefore never carries a 2100 tail it will not live to see.

Residual maturity is bank-fed (loan tape). Absent it, a DISCLOSED default tenor is used and the source is
flagged ('fed' vs 'assumed') — never hidden. Everything here is versioned (EL_VERSION).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from ml.scoring.valuation_discount import collateral_haircut_pct
from services.intelligence.horizon import NOW_YEAR, label_year, lerp
from services.intelligence.insurance_pricing import PricingParams, annual_loss_probability

EL_VERSION = "el-v1.0"
DEFAULT_TENOR_YEARS = 5          # disclosed assumption used only when residual maturity is not fed
DISCOUNT_RATE = 0.0              # kept explicit; undiscounted by default


def annual_expected_loss(ead: Optional[float], score: Optional[float],
                         hazard: Optional[str] = None, attrs: Optional[dict] = None,
                         params: Optional[PricingParams] = None) -> dict:
    """Expected loss over the next 12 months = EAD × P(event/yr) × damage-ratio. Components returned so the
    UI can show the decomposition (frequency × severity × exposure)."""
    if not ead or score is None:
        return {"annual_el_eur": 0.0, "p_event": 0.0, "damage_ratio": 0.0}
    params = params or PricingParams()
    p = annual_loss_probability(score, params)
    # Severity for a LENDING book = collateral-value impairment (the disclosed haircut schedule, vulnerability-
    # adjusted) — NOT the insurance PML worst-case, which would over-state a secured-loan loss. This is a physical
    # collateral-impairment expected loss, not a Basel/IFRS-9 credit ECL (which needs a PD we don't hold).
    dr = collateral_haircut_pct(score, None, hazard, "universal", attrs) / 100.0
    return {"annual_el_eur": round(ead * p * dr, 2), "p_event": round(p, 4), "damage_ratio": round(dr, 4)}


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


def lifetime_expected_loss(ead: Optional[float], nodes: dict, tenor_years: float,
                           hazard: Optional[str] = None, attrs: Optional[dict] = None,
                           discount: float = DISCOUNT_RATE) -> float:
    """Sum the annual EL over the loan's remaining life (maturity-matched). Each year uses the mid-year
    interpolated score, so risk that only bites past the loan's maturity is correctly excluded."""
    if not ead or not nodes or tenor_years <= 0:
        return 0.0
    total = 0.0
    for y in range(int(round(tenor_years))):
        sc = score_at_year(y + 0.5, nodes)          # mid-year score
        if sc is None:
            continue
        el = annual_expected_loss(ead, sc, hazard, attrs)["annual_el_eur"]
        total += el / ((1.0 + discount) ** y)
    return round(total, 2)


def bank_expected_loss(session, org_id: str, scenario: str = "disorderly_2c",
                       default_tenor: float = DEFAULT_TENOR_YEARS) -> dict:
    """Portfolio climate expected loss for a banking book: per-loan annual EL (next 12 months) and lifetime EL
    over the loan's REMAINING life (maturity-matched), rolled up. EAD = outstanding loan balance; residual
    maturity is loan-tape-fed (ext_banking) and flagged 'fed' vs 'assumed'."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (e.entity_id, v.time_horizon)
               e.entity_id::text AS eid, e.entity_name,
               CAST(x.outstanding_loan_balance_eur AS FLOAT) AS ead,
               CAST(x.residual_maturity_years AS FLOAT)     AS tenor,
               e.construction_type, e.year_built, e.number_of_stories,
               v.time_horizon AS horz, v.hazard_type AS hazard, v.physical_risk_score AS sc
        FROM portfolio_entities e
        JOIN v_portfolio_entity_physical_risk v ON v.entity_id = e.entity_id
        LEFT JOIN ext_banking x ON x.entity_id = e.entity_id
        WHERE e.org_id = :o AND e.vertical = 'banking' AND v.hazard_type <> 'heat_acute'
          AND ( (v.scenario = :scen AND v.time_horizon <> 'current')
                OR (v.scenario = 'baseline' AND v.time_horizon = 'current') )
        ORDER BY e.entity_id, v.time_horizon, v.physical_risk_score DESC
    """), {"o": org_id, "scen": scenario}).mappings().all()

    ent: dict = {}
    for r in rows:
        d = ent.setdefault(r["eid"], {
            "name": r["entity_name"], "ead": r["ead"] or 0.0, "tenor": r["tenor"],
            "attrs": {"construction_type": r["construction_type"], "year_built": r["year_built"],
                      "number_of_stories": r["number_of_stories"]},
            "nodes": {}, "haz": {}})
        d["nodes"][label_year(r["horz"])] = r["sc"]
        d["haz"][label_year(r["horz"])] = r["hazard"]

    assets, tot_ead = [], 0.0
    tot_annual = tot_life = 0.0
    fed = assumed = 0
    for eid, d in ent.items():
        ead = d["ead"]
        if not ead:
            continue
        now_score = d["nodes"].get(NOW_YEAR)
        now_haz = d["haz"].get(NOW_YEAR) or next(iter(d["haz"].values()), None)
        tenor = d["tenor"] if d["tenor"] and d["tenor"] > 0 else default_tenor
        tenor_fed = bool(d["tenor"] and d["tenor"] > 0)
        fed += tenor_fed
        assumed += (not tenor_fed)
        ann = annual_expected_loss(ead, now_score, now_haz, d["attrs"])
        life = lifetime_expected_loss(ead, d["nodes"], tenor, now_haz, d["attrs"])
        tot_ead += ead
        tot_annual += ann["annual_el_eur"]
        tot_life += life
        assets.append({
            "entity_id": eid, "entity_name": d["name"], "ead_eur": round(ead, 2),
            "annual_el_eur": ann["annual_el_eur"], "lifetime_el_eur": life,
            "p_event": ann["p_event"], "damage_ratio": ann["damage_ratio"],
            "tenor_years": round(tenor, 1), "tenor_source": "fed" if tenor_fed else "assumed",
            "hazard": now_haz, "el_pct_of_ead": round(100 * life / ead, 2) if ead else 0.0,
        })
    assets.sort(key=lambda a: -a["lifetime_el_eur"])
    return {
        "version": EL_VERSION, "scenario": scenario,
        "total_ead_eur": round(tot_ead, 2),
        "annual_el_eur": round(tot_annual, 2),
        "lifetime_el_eur": round(tot_life, 2),
        "annual_el_bps": round(1e4 * tot_annual / tot_ead, 1) if tot_ead else 0.0,
        "lifetime_el_bps": round(1e4 * tot_life / tot_ead, 1) if tot_ead else 0.0,
        "n_assets": len(assets),
        "maturity_fed": fed, "maturity_assumed": assumed, "default_tenor_years": default_tenor,
        "assets": assets,
        "basis": ("Physical climate expected loss = exposure × P(event/yr) × collateral-impairment severity. "
                  "P(event) from the platform loss curve (annual_loss_probability); severity from the disclosed "
                  "collateral-haircut schedule (df-v1.0, vulnerability-adjusted). Lifetime EL accumulates annual EL "
                  f"over each loan's remaining life (maturity-matched); residual maturity is loan-tape-fed, else a "
                  f"{default_tenor:.0f}-year default is assumed and flagged. This is a physical collateral-impairment "
                  "expectation, NOT a Basel/IFRS-9 credit ECL (no PD is applied). Undiscounted. " + EL_VERSION + "."),
    }
