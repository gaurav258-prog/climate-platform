"""Asset-manager engine — the securities-book analogue of portfolio_engine.

portfolio_engine scores a LOCATED entity (one h3 cell). An asset manager holds
securities whose risk lives one and two hops away:

    fund_positions -> securities -> issuers -> issuer_facilities (many) -> canonical_scores

This module builds the two roll-ups portfolio_engine cannot express:

  1. issuer_physical_scores(): an issuer's physical risk is the MATERIALITY-
     WEIGHTED aggregate of its facilities' per-hazard scores. Facilities with no
     score for a hazard are EXCLUDED from that hazard's average (never imputed as
     zero), and the fraction of the issuer's materiality that is actually scored
     is reported (`scored_weight_pct`) so a thinly-covered issuer is disclosed,
     not silently averaged down. Headline hazard excludes heat_acute, matching
     portfolio_engine's standing convention (one definition of "headline").

  2. fund roll-ups (services layer for the router): value-weight issuer scores by
     position market_value_eur up the fund -> parent-fund hierarchy.

Transition risk (issuer_transition_scores) is joined in the router alongside the
physical score; the transition MODEL that populates that table is Phase 4.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import text

from core.types import score_to_bucket

# Same standing rule as portfolio_engine: heat_acute (today's live ERA5 reading)
# is kept out of the headline selection, though it stays in the per-hazard detail.
EXCLUDE_HEADLINE_HAZARDS = ("heat_acute",)


def issuer_physical_scores(
    session, scenario: str, horizon: str, issuer_ids: Optional[list[str]] = None
) -> dict[str, dict]:
    """issuer_id -> physical-risk summary, materiality-weighted across facilities.

    Returns per issuer:
      per_hazard: {hazard: {"score": weighted, "bucket", "scored_weight": w}}
      headline_score / headline_bucket / headline_hazard  (excl. heat_acute)
      n_facilities / n_scored_facilities / scored_weight_pct  (coverage, disclosed)
    """
    where_issuer = "AND f.issuer_id = ANY(:ids)" if issuer_ids else ""
    rows = session.execute(text(f"""
        SELECT v.issuer_id::text AS issuer_id, v.facility_id::text AS facility_id,
               v.hazard_type, v.physical_risk_score AS score, v.materiality_weight
        FROM   v_issuer_facility_physical_risk v
        JOIN   issuer_facilities f ON f.facility_id = v.facility_id
        WHERE  v.scenario = :s AND v.time_horizon = :h {where_issuer}
    """), {"s": scenario, "h": horizon, **({"ids": issuer_ids} if issuer_ids else {})}).mappings().all()

    # total materiality + facility count per issuer (denominator for coverage), from ALL facilities
    fac_meta = session.execute(text(f"""
        SELECT issuer_id::text AS issuer_id, COUNT(*) AS n_facilities,
               COALESCE(SUM(materiality_weight), 0) AS total_weight
        FROM   issuer_facilities f
        WHERE  TRUE {where_issuer}
        GROUP  BY issuer_id
    """), ({"ids": issuer_ids} if issuer_ids else {})).mappings().all()
    meta = {m["issuer_id"]: {"n_facilities": m["n_facilities"], "total_weight": float(m["total_weight"] or 0)}
            for m in fac_meta}

    # accumulate weighted score per (issuer, hazard), and the set of scored facilities per issuer
    acc: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])  # [Σ w·score, Σ w]
    scored_facilities: dict[str, set] = defaultdict(set)
    scored_weight_by_issuer: dict[str, dict] = defaultdict(dict)  # issuer -> {facility_id: weight} (dedup for coverage)
    for r in rows:
        w = float(r["materiality_weight"] or 0)
        a = acc[(r["issuer_id"], r["hazard_type"])]
        a[0] += w * float(r["score"]); a[1] += w
        scored_facilities[r["issuer_id"]].add(r["facility_id"])
        scored_weight_by_issuer[r["issuer_id"]][r["facility_id"]] = w

    out: dict[str, dict] = {}
    for issuer_id, m in meta.items():
        per_hazard = {}
        for (iid, hazard), (wsum, wtot) in acc.items():
            if iid != issuer_id or wtot <= 0:
                continue
            score = round(wsum / wtot, 1)
            per_hazard[hazard] = {"score": score, "bucket": score_to_bucket(score).value,
                                   "scored_weight": round(wtot, 4)}
        priceable = {h: v for h, v in per_hazard.items() if h not in EXCLUDE_HEADLINE_HAZARDS}
        headline_hazard = max(priceable, key=lambda h: priceable[h]["score"]) if priceable else None
        headline = per_hazard.get(headline_hazard) if headline_hazard else None
        scored_weight = sum(scored_weight_by_issuer[issuer_id].values())
        out[issuer_id] = {
            "per_hazard": per_hazard,
            "headline_score": headline["score"] if headline else None,
            "headline_bucket": headline["bucket"] if headline else None,
            "headline_hazard": headline_hazard,
            "n_facilities": m["n_facilities"],
            "n_scored_facilities": len(scored_facilities.get(issuer_id, ())),
            "scored_weight_pct": round(100 * scored_weight / m["total_weight"], 1) if m["total_weight"] else 0.0,
        }
    return out


def issuer_transition_scores(
    session, scenario: str, horizon: str, issuer_ids: Optional[list[str]] = None
) -> dict[str, dict]:
    """issuer_id -> current transition-risk row (valid_to IS NULL). Empty until the
    Phase-4 model populates issuer_transition_scores — an honest absence, never a
    fabricated zero."""
    where_issuer = "AND issuer_id = ANY(:ids)" if issuer_ids else ""
    rows = session.execute(text(f"""
        SELECT issuer_id::text AS issuer_id,
               CAST(transition_risk_score AS FLOAT) AS transition_risk_score, risk_bucket,
               CAST(carbon_intensity_tco2e_per_meur AS FLOAT) AS carbon_intensity_tco2e_per_meur,
               CAST(stranded_asset_pct AS FLOAT) AS stranded_asset_pct,
               CAST(carbon_price_impact_eur AS FLOAT) AS carbon_price_impact_eur,
               model_version, data_vintage
        FROM   issuer_transition_scores
        WHERE  scenario = :s AND time_horizon = :h AND valid_to IS NULL {where_issuer}
    """), {"s": scenario, "h": horizon, **({"ids": issuer_ids} if issuer_ids else {})}).mappings().all()
    return {r["issuer_id"]: dict(r) for r in rows}


def fund_descendant_ids(session, fund_id: str) -> list[str]:
    """A fund plus every sub-fund/sub-portfolio beneath it (recursive hierarchy).
    A fund-of-funds' exposure is the union of its children's positions."""
    rows = session.execute(text("""
        WITH RECURSIVE tree AS (
            SELECT fund_id FROM funds WHERE fund_id = :f
            UNION ALL
            SELECT c.fund_id FROM funds c JOIN tree t ON c.parent_fund_id = t.fund_id
        )
        SELECT fund_id::text AS fund_id FROM tree
    """), {"f": fund_id}).scalars().all()
    return [str(x) for x in rows]


def fund_positions_with_risk(session, fund_id: str, scenario: str, horizon: str,
                              as_of_date: Optional[str] = None) -> list[dict]:
    """Every position in a fund (and its sub-funds), each enriched with its
    issuer's materiality-weighted physical score and its transition score.
    Value-weighting for roll-ups is done by the caller on market_value_eur."""
    fund_ids = fund_descendant_ids(session, fund_id)
    if not fund_ids:
        return []
    date_filter = "AND p.as_of_date = :d" if as_of_date else """
        AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)"""
    positions = session.execute(text(f"""
        SELECT p.position_id::text AS position_id, p.fund_id::text AS fund_id,
               CAST(p.market_value_eur AS FLOAT) AS market_value_eur,
               CAST(p.weight_pct AS FLOAT) AS weight_pct, p.as_of_date::text AS as_of_date,
               s.security_id::text AS security_id, s.isin, s.name AS security_name,
               s.asset_class, s.currency,
               i.issuer_id::text AS issuer_id, i.name AS issuer_name, i.issuer_type,
               i.country, i.sector, i.nace_code
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        JOIN   issuers    i ON i.issuer_id = s.issuer_id
        WHERE  p.fund_id = ANY(:fids) {date_filter}
    """), {"fids": fund_ids, **({"d": as_of_date} if as_of_date else {})}).mappings().all()
    if not positions:
        return []

    issuer_ids = list({p["issuer_id"] for p in positions})
    phys = issuer_physical_scores(session, scenario, horizon, issuer_ids)
    trans = issuer_transition_scores(session, scenario, horizon, issuer_ids)

    out = []
    for p in positions:
        ph = phys.get(p["issuer_id"], {})
        tr = trans.get(p["issuer_id"])
        out.append({
            **{k: p[k] for k in p.keys()},
            "physical": {
                "headline_score": ph.get("headline_score"),
                "headline_bucket": ph.get("headline_bucket"),
                "headline_hazard": ph.get("headline_hazard"),
                "per_hazard": ph.get("per_hazard", {}),
                "scored_weight_pct": ph.get("scored_weight_pct", 0.0),
                "n_facilities": ph.get("n_facilities", 0),
                "n_scored_facilities": ph.get("n_scored_facilities", 0),
            },
            "transition": tr,  # None until Phase-4 model runs — honest absence
        })
    return out
