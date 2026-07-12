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


def fund_esg_pai(session, fund_id: str) -> dict:
    """SFDR PAI 5-14 (the non-carbon indicators) for a fund, from issuer_esg_metrics.

    Method, per RTS shape and our honesty rules:
      * ratios (5 energy share, 6 energy intensity, 12 pay gap, 13 board diversity)
        → value-weighted average over the value that actually has the datum.
      * flags (7 biodiversity, 10 violations, 11 no-monitoring, 14 weapons)
        → share of value exposed, over the value where the flag is known.
      * absolutes (8 water, 9 waste) → PCAF-attributed per €M invested (needs EVIC).
    Each indicator reports its own coverage; missing data is a gap, not a zero.
    """
    org_id = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    fund_ids = fund_descendant_ids(session, fund_id)
    if not fund_ids:
        return {}
    rows = session.execute(text("""
        SELECT CAST(p.market_value_eur AS FLOAT) AS mv, CAST(em.evic_eur AS FLOAT) AS evic,
               CAST(e.non_renewable_energy_pct AS FLOAT) AS non_renew,
               CAST(e.energy_intensity_gwh_per_meur AS FLOAT) AS energy_int,
               e.biodiversity_sensitive_ops AS biodiv,
               CAST(e.emissions_to_water_tonnes AS FLOAT) AS water,
               CAST(e.hazardous_waste_tonnes AS FLOAT) AS waste,
               e.ungc_oecd_violation AS violation, e.ungc_oecd_no_monitoring AS no_monitor,
               CAST(e.gender_pay_gap_pct AS FLOAT) AS pay_gap,
               CAST(e.board_female_pct AS FLOAT) AS board_f, e.controversial_weapons AS weapons
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        LEFT   JOIN LATERAL (
            SELECT * FROM issuer_esg_metrics
            WHERE issuer_id = s.issuer_id AND (org_id = :org OR org_id IS NULL)
            ORDER BY (org_id IS NULL), reporting_year DESC LIMIT 1
        ) e ON TRUE
        LEFT   JOIN LATERAL (
            SELECT evic_eur FROM issuer_emissions
            WHERE issuer_id = s.issuer_id AND (org_id = :org OR org_id IS NULL) AND evic_eur IS NOT NULL
            ORDER BY (org_id IS NULL), reporting_year DESC LIMIT 1
        ) em ON TRUE
        WHERE  p.fund_id = ANY(:fids)
          AND  p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
    """), {"fids": fund_ids, "org": org_id}).mappings().all()

    total_mv = sum(r["mv"] for r in rows) or 0.0
    if total_mv == 0:
        return {}

    def wavg(field):
        cov = [(r["mv"], r[field]) for r in rows if r[field] is not None]
        w = sum(mv for mv, _ in cov)
        return (round(sum(mv * v for mv, v in cov) / w, 2), round(100 * w / total_mv, 1)) if w else (None, 0.0)

    def share(field):
        known = [(r["mv"], r[field]) for r in rows if r[field] is not None]
        w = sum(mv for mv, _ in known)
        return (round(100 * sum(mv for mv, v in known if v) / w, 2), round(100 * w / total_mv, 1)) if w else (None, 0.0)

    def attributed_per_meur(field):
        cov = [(r["mv"], r["evic"], r[field]) for r in rows if r[field] is not None and r["evic"]]
        inv = sum(mv for mv, _, _ in cov)
        if not inv:
            return None, 0.0
        attributed = sum((mv / evic) * v for mv, evic, v in cov)
        return round(attributed / (inv / 1e6), 3), round(100 * inv / total_mv, 1)

    return {
        "pai_5": dict(zip(("value", "coverage_pct"), wavg("non_renew"))),
        "pai_6": dict(zip(("value", "coverage_pct"), wavg("energy_int"))),
        "pai_7": dict(zip(("value", "coverage_pct"), share("biodiv"))),
        "pai_8": dict(zip(("value", "coverage_pct"), attributed_per_meur("water"))),
        "pai_9": dict(zip(("value", "coverage_pct"), attributed_per_meur("waste"))),
        "pai_10": dict(zip(("value", "coverage_pct"), share("violation"))),
        "pai_11": dict(zip(("value", "coverage_pct"), share("no_monitor"))),
        "pai_12": dict(zip(("value", "coverage_pct"), wavg("pay_gap"))),
        "pai_13": dict(zip(("value", "coverage_pct"), wavg("board_f"))),
        "pai_14": dict(zip(("value", "coverage_pct"), share("weapons"))),
    }


def _positions_with_emissions(session, fund_id: str, as_of_date: Optional[str]):
    fund_ids = fund_descendant_ids(session, fund_id)
    if not fund_ids:
        return []
    # The fund's own org: its private issuer disclosures take precedence over any
    # global/estimated fallback (org_id IS NULL) for that same issuer.
    org_id = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    date_filter = "AND p.as_of_date = :d" if as_of_date else """
        AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)"""
    return session.execute(text(f"""
        SELECT p.position_id::text AS position_id,
               CAST(p.market_value_eur AS FLOAT) AS mv,
               i.issuer_id::text AS issuer_id, i.name AS issuer_name, i.nace_code,
               CAST(e.scope1_tco2e AS FLOAT) AS s1, CAST(e.scope2_tco2e AS FLOAT) AS s2,
               CAST(e.scope3_tco2e AS FLOAT) AS s3, CAST(e.revenue_eur AS FLOAT) AS revenue_eur,
               CAST(e.evic_eur AS FLOAT) AS evic_eur, e.source AS emissions_source
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        JOIN   issuers    i ON i.issuer_id = s.issuer_id
        LEFT   JOIN LATERAL (
            SELECT scope1_tco2e, scope2_tco2e, scope3_tco2e, revenue_eur, evic_eur, source
            FROM issuer_emissions
            WHERE issuer_id = i.issuer_id AND (org_id = :org OR org_id IS NULL)
            -- prefer a row that actually carries scope figures (real or estimated)
            -- over a revenue-only row, then this org's own over the global fallback,
            -- then most recent year.
            ORDER BY (scope1_tco2e IS NULL), (org_id IS NULL), reporting_year DESC LIMIT 1
        ) e ON TRUE
        WHERE  p.fund_id = ANY(:fids) {date_filter}
    """), {"fids": fund_ids, "org": org_id, **({"d": as_of_date} if as_of_date else {})}).mappings().all()


def fund_pai(session, fund_id: str) -> dict:
    """SFDR PAI table + coverage for a fund, value-weighted. Honest gaps, not zeros."""
    rows = _positions_with_emissions(session, fund_id, None)
    total_mv = sum(r["mv"] for r in rows) or 0.0
    if total_mv == 0:
        return {"total_value_eur": 0, "positions": 0}

    with_emissions = [r for r in rows if r["s1"] is not None and r["revenue_eur"]]
    covered_mv = sum(r["mv"] for r in with_emissions)
    # SFDR requires disclosing the estimated-vs-reported split.
    estimated_mv = sum(r["mv"] for r in with_emissions if r.get("emissions_source") == "estimated")

    # PCAF data-quality score (1 best … 5 worst), value-weighted over covered value.
    # reported (disclosed/client/cdp) → 2 (reported, unverified); vendor → 3;
    # estimated (economic-activity, sector-intensity × revenue) → 4.
    _PCAF_DQ = {"disclosed": 2, "client": 2, "cdp": 2, "vendor": 3, "estimated": 4}
    dq_num = sum(r["mv"] * _PCAF_DQ.get(r.get("emissions_source"), 4) for r in with_emissions)
    pcaf_dq = round(dq_num / covered_mv, 1) if covered_mv else None

    # PAI 3 — WACI: Σ (position weight × issuer carbon intensity). Weighted over
    # the COVERED value (renormalized), and coverage disclosed separately.
    waci = None
    if covered_mv:
        waci = sum(r["mv"] * ((r["s1"] + (r["s2"] or 0)) / (r["revenue_eur"] / 1e6))
                   for r in with_emissions) / covered_mv

    # PAI 1 — financed emissions (PCAF): attribution factor = investment ÷ EVIC.
    # We now attribute for every holding that has EVIC, and disclose the coverage;
    # the un-attributed investee totals remain for holdings without EVIC.
    investee_s1 = sum(r["s1"] for r in with_emissions)
    investee_s2 = sum((r["s2"] or 0) for r in with_emissions)
    investee_s3 = sum((r["s3"] or 0) for r in with_emissions)

    with_evic = [r for r in with_emissions if r.get("evic_eur")]
    financed_mv = sum(r["mv"] for r in with_evic)
    fin_s1 = fin_s2 = fin_s3 = 0.0
    for r in with_evic:
        af = r["mv"] / r["evic_eur"]            # attribution factor
        fin_s1 += af * r["s1"]
        fin_s2 += af * (r["s2"] or 0)
        fin_s3 += af * (r["s3"] or 0)
    financed_total = fin_s1 + fin_s2 + fin_s3
    has_financed = financed_mv > 0
    # PAI 2 — carbon footprint = financed emissions ÷ €M invested (over EVIC-covered value).
    carbon_footprint = round(financed_total / (financed_mv / 1e6), 1) if has_financed else None

    # PAI 4 — fossil-fuel-sector exposure %
    fossil_mv = sum(r["mv"] for r in rows
                    if r["nace_code"] and r["nace_code"].strip()[:2] in FOSSIL_FUEL_NACE_DIVISIONS)

    return {
        "total_value_eur": round(total_mv),
        "positions": len(rows),
        "emissions_coverage_pct": round(100 * covered_mv / total_mv, 1),
        "emissions_estimated_pct": round(100 * estimated_mv / covered_mv, 1) if covered_mv else 0.0,
        "pcaf_data_quality_score": pcaf_dq,   # PCAF 1(best)–5(worst), value-weighted over covered
        "financed_emissions_coverage_pct": round(100 * financed_mv / total_mv, 1) if total_mv else 0.0,
        "pai": {
            "pai_3_waci_tco2e_per_meur": round(waci, 1) if waci is not None else None,
            "pai_4_fossil_fuel_exposure_pct": round(100 * fossil_mv / total_mv, 2),
            # PAI 1 — financed emissions, attributed via EVIC where available.
            "pai_1_financed_emissions_tco2e": {
                "scope_1": round(fin_s1), "scope_2": round(fin_s2), "scope_3": round(fin_s3),
                "total": round(financed_total),
            } if has_financed else None,
            # PAI 2 — carbon footprint (financed emissions per €M invested).
            "pai_2_carbon_footprint_tco2e_per_meur": carbon_footprint,
            "pai_1_investee_emissions_tco2e": {
                "scope_1": round(investee_s1), "scope_2": round(investee_s2), "scope_3": round(investee_s3),
                "note": None if has_financed and financed_mv >= covered_mv else
                        "Un-attributed investee totals; supply issuer EVIC on the remaining "
                        "holdings to attribute their financed emissions (PCAF).",
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
