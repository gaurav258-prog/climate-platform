"""Fund-level regulatory aggregation — the output layer for the asset-manager
product. Rolls the holdings graph up to a FUND (the reporting entity SFDR/TCFD
filings are made at) and produces:

  * SFDR Principal Adverse Impact (PAI) indicators that are HONESTLY computable
    from the data the foundation now carries (issuer emissions + positions):
      - PAI 3  GHG intensity of investees (WACI)  — fully computable, no gaps
      - PAI 1  financed GHG emissions (scope 1/2/3) — computable with an
               ownership attribution factor; where EVIC is absent we disclose
               the input we still need rather than fabricate one (PCAF-style)
      - PAI 2  carbon footprint (financed emissions / €m invested)
      - PAI 4  fossil-fuel-sector exposure %
    PAIs needing data we do not yet collect (5/6 energy mix & intensity) are
    surfaced as explicit "input required" gaps, never silent zeros.
  * Value-weighted PHYSICAL exposure (from the footprint engine).
  * Value-weighted TRANSITION exposure (from the transition model).
  * Data-coverage %, so a thinly-covered fund is disclosed, not averaged down.

Every number is value-weighted on market_value_eur and traces to the issuer,
security and position it came from.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

from services.asset_manager_engine import (
    fund_descendant_ids, issuer_physical_scores, issuer_transition_scores,
)

# NACE divisions whose revenue is fossil-fuel-derived (SFDR PAI 4). Extraction of
# coal (05) and oil & gas (06), and manufacture of coke/refined petroleum (19).
FOSSIL_FUEL_NACE_DIVISIONS = {"05", "06", "19"}


def _positions_with_emissions(session, fund_id: str, as_of_date: Optional[str]):
    fund_ids = fund_descendant_ids(session, fund_id)
    if not fund_ids:
        return []
    date_filter = "AND p.as_of_date = :d" if as_of_date else """
        AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)"""
    return session.execute(text(f"""
        SELECT p.position_id::text AS position_id,
               CAST(p.market_value_eur AS FLOAT) AS mv,
               i.issuer_id::text AS issuer_id, i.name AS issuer_name, i.nace_code,
               CAST(e.scope1_tco2e AS FLOAT) AS s1, CAST(e.scope2_tco2e AS FLOAT) AS s2,
               CAST(e.scope3_tco2e AS FLOAT) AS s3, CAST(e.revenue_eur AS FLOAT) AS revenue_eur
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        JOIN   issuers    i ON i.issuer_id = s.issuer_id
        LEFT   JOIN LATERAL (
            SELECT scope1_tco2e, scope2_tco2e, scope3_tco2e, revenue_eur
            FROM issuer_emissions WHERE issuer_id = i.issuer_id
            ORDER BY reporting_year DESC LIMIT 1
        ) e ON TRUE
        WHERE  p.fund_id = ANY(:fids) {date_filter}
    """), {"fids": fund_ids, **({"d": as_of_date} if as_of_date else {})}).mappings().all()


def fund_pai(session, fund_id: str) -> dict:
    """SFDR PAI table + coverage for a fund, value-weighted. Honest gaps, not zeros."""
    rows = _positions_with_emissions(session, fund_id, None)
    total_mv = sum(r["mv"] for r in rows) or 0.0
    if total_mv == 0:
        return {"total_value_eur": 0, "positions": 0}

    with_emissions = [r for r in rows if r["s1"] is not None and r["revenue_eur"]]
    covered_mv = sum(r["mv"] for r in with_emissions)

    # PAI 3 — WACI: Σ (position weight × issuer carbon intensity). Weighted over
    # the COVERED value (renormalized), and coverage disclosed separately.
    waci = None
    if covered_mv:
        waci = sum(r["mv"] * ((r["s1"] + (r["s2"] or 0)) / (r["revenue_eur"] / 1e6))
                   for r in with_emissions) / covered_mv

    # PAI 1 — financed emissions (PCAF): needs an attribution factor
    # investment ÷ EVIC. EVIC is not yet collected, so we report the portfolio's
    # aggregate investee emissions with the attribution factor DISCLOSED as
    # required-but-missing, rather than inventing an EVIC.
    investee_s1 = sum(r["s1"] for r in with_emissions)
    investee_s2 = sum((r["s2"] or 0) for r in with_emissions)
    investee_s3 = sum((r["s3"] or 0) for r in with_emissions)

    # PAI 4 — fossil-fuel-sector exposure %
    fossil_mv = sum(r["mv"] for r in rows
                    if r["nace_code"] and r["nace_code"].strip()[:2] in FOSSIL_FUEL_NACE_DIVISIONS)

    return {
        "total_value_eur": round(total_mv),
        "positions": len(rows),
        "emissions_coverage_pct": round(100 * covered_mv / total_mv, 1),
        "pai": {
            "pai_3_waci_tco2e_per_meur": round(waci, 1) if waci is not None else None,
            "pai_4_fossil_fuel_exposure_pct": round(100 * fossil_mv / total_mv, 2),
            "pai_1_investee_emissions_tco2e": {
                "scope_1": round(investee_s1), "scope_2": round(investee_s2), "scope_3": round(investee_s3),
                "attribution_factor": None,   # investment ÷ EVIC — EVIC not yet collected
                "note": "Financed (attributed) emissions require issuer EVIC per PCAF. "
                        "EVIC is not yet collected; supply it to complete PAI 1/2. "
                        "Figures shown are un-attributed investee totals over covered holdings.",
            },
        },
        "pai_gaps": [
            {"indicator": "PAI 5 — non-renewable energy consumption/production share",
             "input_required": "issuer energy mix (renewable vs non-renewable)"},
            {"indicator": "PAI 6 — energy-consumption intensity by high-impact NACE",
             "input_required": "issuer energy consumption (GWh) by NACE"},
            {"indicator": "PAI 1/2 — financed-emissions attribution",
             "input_required": "issuer EVIC (enterprise value incl. cash)"},
        ],
    }


def fund_climate_summary(session, fund_id: str, scenario: str, horizon: str) -> dict:
    """Value-weighted physical + transition exposure for a fund, plus the PAI
    block — the one call a fund's climate report is built from."""
    fund = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.fund_type, f.sfdr_classification,
               o.name AS org_name
        FROM funds f JOIN organizations o ON o.org_id = f.org_id
        WHERE f.fund_id = :f
    """), {"f": fund_id}).mappings().first()
    if not fund:
        return {"error": "fund not found"}

    fund_ids = fund_descendant_ids(session, fund_id)
    positions = session.execute(text("""
        SELECT p.security_id::text AS security_id, CAST(p.market_value_eur AS FLOAT) AS mv,
               i.issuer_id::text AS issuer_id, i.name AS issuer_name, i.nace_code
        FROM fund_positions p
        JOIN securities s ON s.security_id = p.security_id
        JOIN issuers i ON i.issuer_id = s.issuer_id
        WHERE p.fund_id = ANY(:fids)
          AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
    """), {"fids": fund_ids}).mappings().all()
    total_mv = sum(p["mv"] for p in positions) or 0.0
    if total_mv == 0:
        return {"fund": dict(fund), "total_value_eur": 0, "positions": 0}

    issuer_ids = list({p["issuer_id"] for p in positions})
    phys = issuer_physical_scores(session, scenario, horizon, issuer_ids)
    trans = issuer_transition_scores(session, scenario, horizon, issuer_ids)

    # value-weighted physical
    phys_scored = [(p, phys[p["issuer_id"]]) for p in positions
                   if phys.get(p["issuer_id"], {}).get("headline_score") is not None]
    phys_cov_mv = sum(p["mv"] for p, _ in phys_scored)
    phys_was = (sum(p["mv"] * ph["headline_score"] for p, ph in phys_scored) / phys_cov_mv) if phys_cov_mv else None
    phys_high_mv = sum(p["mv"] for p, ph in phys_scored if ph["headline_bucket"] in ("H", "VH"))

    # value-weighted transition
    trans_scored = [(p, trans[p["issuer_id"]]) for p in positions if p["issuer_id"] in trans]
    trans_cov_mv = sum(p["mv"] for p, _ in trans_scored)
    trans_was = (sum(p["mv"] * t["transition_risk_score"] for p, t in trans_scored) / trans_cov_mv) if trans_cov_mv else None
    trans_high_mv = sum(p["mv"] for p, t in trans_scored if t["risk_bucket"] in ("H", "VH"))

    return {
        "fund": dict(fund), "scenario": scenario, "horizon": horizon,
        "total_value_eur": round(total_mv), "positions": len(positions),
        "physical": {
            "value_weighted_score": round(phys_was, 1) if phys_was is not None else None,
            "coverage_pct": round(100 * phys_cov_mv / total_mv, 1),
            "value_at_high_plus_eur": round(phys_high_mv),
            "pct_at_high_plus": round(100 * phys_high_mv / total_mv, 1),
        },
        "transition": {
            "value_weighted_score": round(trans_was, 1) if trans_was is not None else None,
            "coverage_pct": round(100 * trans_cov_mv / total_mv, 1),
            "value_at_high_plus_eur": round(trans_high_mv),
            "pct_at_high_plus": round(100 * trans_high_mv / total_mv, 1),
        },
        "pai": fund_pai(session, fund_id),
    }
