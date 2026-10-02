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
    fund_descendant_ids,
    issuer_physical_scores,
    issuer_transition,
)

# NACE codes whose revenue is fossil-fuel-derived (SFDR PAI 4). Scoped to Art. 2(62)
# of Regulation (EU) 2018/1999: exploration, mining, extraction, production,
# processing, storage, refining, distribution, transportation, trade of fossil
# fuels — broader than extraction+refining alone.
#   Divisions (2-digit, matched by leading digits of the NACE code):
#     05 coal extraction, 06 oil & gas extraction, 19 coke/refined petroleum
#   Classes (4-digit, matched by leading digits so a division-level holding code
#     still falls through to the broader division set above when it is coarser):
#     35.2  manufacture of gas / distribution of gaseous fuels via mains
#     46.71 wholesale of solid, liquid and gaseous fuels and related products
#     47.30 retail sale of automotive fuel
#     49.50 transport via pipeline
#     52.10 warehousing and storage
FOSSIL_FUEL_NACE_DIVISIONS = {"05", "06", "19"}
FOSSIL_FUEL_NACE_CLASSES = {"35.2", "46.71", "47.30", "49.50", "52.10"}


def _is_fossil_fuel_nace(nace_code) -> bool:
    """True if a holding's NACE code falls in the fossil-fuel scope (SFDR PAI 4 /
    Art. 2(62) of Reg. (EU) 2018/1999): division-level match for extraction/coke-
    petroleum (05/06/19), class-level (prefix) match for the broader distribution/
    trade/transport/storage codes added to cover the full value chain. NACE codes
    in the golden source appear both dotted ("35.20") and undotted ("3520"/"0610"),
    so matching strips the dot before comparing digit prefixes."""
    if not nace_code:
        return False
    digits = nace_code.strip().replace(".", "")
    if digits[:2] in FOSSIL_FUEL_NACE_DIVISIONS:
        return True
    return any(digits.startswith(cls.replace(".", "")) for cls in FOSSIL_FUEL_NACE_CLASSES)


def fund_esg_pai(session, fund_id: str, *, fund_ids=None, org_id=None, as_of=None) -> dict:
    """SFDR PAI 5-14 (the non-carbon indicators) for a fund, from issuer_esg_metrics.
    Pass fund_ids+org_id to scope over an entire manager (entity-level roll-up).

    Method, per RTS shape and our honesty rules:
      * ratios (5 energy share, 6 energy intensity, 12 pay gap, 13 board diversity)
        → value-weighted average over the value that actually has the datum.
      * flags (7 biodiversity, 10 violations, 11 no-monitoring, 14 weapons)
        → share of value exposed, over the value where the flag is known.
      * absolutes (8 water, 9 waste) → PCAF-attributed per €M invested (needs EVIC).
    Each indicator reports its own coverage; missing data is a gap, not a zero.
    as_of: the holdings date (default: each fund's latest).
    """
    if org_id is None:
        org_id = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    if fund_ids is None:
        fund_ids = fund_descendant_ids(session, fund_id)
    if not fund_ids:
        return {}
    rows = session.execute(text("""
        SELECT CAST(p.market_value_eur AS FLOAT) AS mv, CAST(em.evic_eur AS FLOAT) AS evic,
               i.issuer_id::text AS issuer_id, i.name AS issuer_name, i.nace_code, i.country, CAST(rv.revenue_eur AS FLOAT) AS revenue_eur,
               CAST(e.non_renewable_energy_pct AS FLOAT) AS non_renew,
               CAST(e.non_renewable_consumption_pct AS FLOAT) AS nr_cons,
               CAST(e.non_renewable_production_pct AS FLOAT) AS nr_prod,
               CAST(e.energy_intensity_gwh_per_meur AS FLOAT) AS energy_int,
               CAST(e.energy_consumption_gwh AS FLOAT) AS energy_gwh,
               e.biodiversity_sensitive_ops AS biodiv,
               CAST(e.emissions_to_water_tonnes AS FLOAT) AS water,
               CAST(e.hazardous_waste_tonnes AS FLOAT) AS waste,
               e.ungc_oecd_violation AS violation, e.ungc_oecd_no_monitoring AS no_monitor,
               CAST(e.gender_pay_gap_pct AS FLOAT) AS pay_gap,
               CAST(e.board_female_pct AS FLOAT) AS board_f, e.controversial_weapons AS weapons
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        JOIN   issuers    i ON i.issuer_id = s.issuer_id
        LEFT   JOIN LATERAL (
            SELECT * FROM issuer_esg_metrics
            WHERE issuer_id = s.issuer_id AND (org_id = :org OR org_id IS NULL) AND (CAST(:ry AS int) IS NULL OR reporting_year <= CAST(:ry AS int))
            ORDER BY (org_id IS NULL), (source = 'vendor'), reporting_year DESC LIMIT 1
        ) e ON TRUE
        LEFT   JOIN LATERAL (
            SELECT evic_eur FROM issuer_emissions
            WHERE issuer_id = s.issuer_id AND (org_id = :org OR org_id IS NULL) AND evic_eur IS NOT NULL AND (CAST(:ry AS int) IS NULL OR reporting_year <= CAST(:ry AS int))
            ORDER BY (org_id IS NULL), (source = 'vendor'), reporting_year DESC LIMIT 1
        ) em ON TRUE
        LEFT   JOIN LATERAL (
            SELECT revenue_eur FROM issuer_emissions
            WHERE issuer_id = s.issuer_id AND (org_id = :org OR org_id IS NULL) AND revenue_eur IS NOT NULL AND (CAST(:ry AS int) IS NULL OR reporting_year <= CAST(:ry AS int))
            ORDER BY (org_id IS NULL), (source = 'estimated'), reporting_year DESC LIMIT 1
        ) rv ON TRUE
        WHERE  p.fund_id = ANY(:fids)
          AND  p.as_of_date = COALESCE(CAST(:as_of AS date), (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id))
    """), {"fids": fund_ids, "org": org_id, "as_of": as_of, "ry": _up_to_year(as_of)}).mappings().all()

    total_mv = sum(r["mv"] for r in rows) or 0.0
    if total_mv == 0:
        return {}
    rows = [dict(r) for r in rows]
    from services.fund_energy import energy_facts, energy_pais, outliers
    energy = energy_facts(rows)

    def wavg(field):
        cov = [(r["mv"], r[field]) for r in rows if r[field] is not None]
        w = sum(mv for mv, _ in cov)
        return (round(sum(mv * v for mv, v in cov) / w, 2), round(100 * w / total_mv, 1)) if w else (None, 0.0)

    def share(field):
        known = [(r["mv"], r[field]) for r in rows if r[field] is not None]
        w = sum(mv for mv, _ in known)
        return (round(100 * sum(mv for mv, v in known if v) / w, 2), round(100 * w / total_mv, 1)) if w else (None, 0.0)

    def attributed_per_meur(field):
        # Annex I Table 1's denominator is the current value of ALL investments
        # (total fund AUM), not just the EVIC-covered subset used to attribute the
        # numerator — coverage (share of value that IS EVIC-attributed) is still
        # disclosed separately via the second tuple element.
        cov = [(r["mv"], r["evic"], r[field]) for r in rows if r[field] is not None and r["evic"] and r["evic"] > 0]
        inv = sum(mv for mv, _, _ in cov)
        if not inv:
            return None, 0.0
        attributed = sum(min(mv / evic, 1.0) * v for mv, evic, v in cov)  # attribution capped at 100%
        return round(attributed / (total_mv / 1e6), 3), round(100 * inv / total_mv, 1)

    return {
        **energy_pais(rows, total_mv, energy),
        "energy_outliers": outliers(session, org_id, rows, energy),
        "pai_7": dict(zip(("value", "coverage_pct"), share("biodiv"))),
        "pai_8": dict(zip(("value", "coverage_pct"), attributed_per_meur("water"))),
        "pai_9": dict(zip(("value", "coverage_pct"), attributed_per_meur("waste"))),
        "pai_10": dict(zip(("value", "coverage_pct"), share("violation"))),
        "pai_11": dict(zip(("value", "coverage_pct"), share("no_monitor"))),
        "pai_12": dict(zip(("value", "coverage_pct"), wavg("pay_gap"))),
        "pai_13": dict(zip(("value", "coverage_pct"), wavg("board_f"))),
        "pai_14": dict(zip(("value", "coverage_pct"), share("weapons"))),
    }


def _positions_with_emissions(session, fund_id: str, as_of_date: Optional[str],
                              *, fund_ids=None, org_id=None):
    # scope override (fund_ids + org_id) lets an entity-level roll-up reuse this
    # exact SQL over ALL of a manager's funds instead of a single fund's subtree.
    if fund_ids is None:
        fund_ids = fund_descendant_ids(session, fund_id)
    if not fund_ids:
        return []
    # The fund's own org: its private issuer disclosures take precedence over any
    # global/estimated fallback (org_id IS NULL) for that same issuer.
    if org_id is None:
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
            WHERE issuer_id = i.issuer_id AND (org_id = :org OR org_id IS NULL) AND (CAST(:ry AS int) IS NULL OR reporting_year <= CAST(:ry AS int))
            -- prefer a row that actually carries scope figures (real or estimated)
            -- over a revenue-only row, then this org's own over the global fallback,
            -- then most recent year.
            ORDER BY (scope1_tco2e IS NULL), (org_id IS NULL), (source = 'vendor'), reporting_year DESC LIMIT 1
        ) e ON TRUE
        WHERE  p.fund_id = ANY(:fids) {date_filter}
    """), {"fids": fund_ids, "org": org_id, "ry": _up_to_year(as_of_date),
           **({"d": as_of_date} if as_of_date else {})}).mappings().all()


def _up_to_year(as_of) -> int | None:
    """An investee's figures for a holdings date: only those reported for that date's year or earlier (a statement for a
    reference period never reads figures for a later year); no date (the live view): each investee's latest."""
    if as_of in (None, ""):
        return None
    return int(str(as_of)[:4])


def _r(v):
    return None if v is None else round(v)


def fund_pai(session, fund_id: str, *, fund_ids=None, org_id=None, as_of=None) -> dict:
    """SFDR PAI table + coverage for a fund, value-weighted. Honest gaps, not zeros.
    Pass fund_ids+org_id to scope over an entire manager (entity-level roll-up); as_of: the holdings date
    (default: each fund's latest)."""
    rows = _positions_with_emissions(session, fund_id, as_of, fund_ids=fund_ids, org_id=org_id)
    total_mv = sum(r["mv"] for r in rows) or 0.0
    if total_mv == 0:
        return {"total_value_eur": 0, "positions": 0}

    # Positive revenue required — a negative/zero revenue would invert or blow up
    # the carbon-intensity ratio, so those holdings are excluded (and disclosed via coverage).
    with_emissions = [r for r in rows if r["s1"] is not None and r["revenue_eur"] and r["revenue_eur"] > 0]
    covered_mv = sum(r["mv"] for r in with_emissions)
    # SFDR requires disclosing the estimated-vs-reported split.
    estimated_mv = sum(r["mv"] for r in with_emissions if r.get("emissions_source") == "estimated")

    # PCAF data-quality score (1 best … 5 worst), value-weighted over covered value.
    # reported (disclosed/client/cdp) → 2 (reported, unverified); vendor → 3;
    # estimated (economic-activity, sector-intensity × revenue) → 4.
    _PCAF_DQ = {"disclosed": 2, "client": 2, "cdp": 2, "vendor": 3, "estimated": 4}
    dq_num = sum(r["mv"] * _PCAF_DQ.get(r.get("emissions_source"), 4) for r in with_emissions)
    pcaf_dq = round(dq_num / covered_mv, 1) if covered_mv else None

    # PAI 3 — WACI: Σ (position weight × issuer carbon intensity). Annex I Table 1's indicator-3 formula
    # (verified verbatim against the actual Official Journal text) is:
    #   Σ ( current value of investment_i / current value of ALL investments (€M) × investee GHG intensity_i )
    # — i.e. the denominator is total fund value, exactly like PAI 2's carbon-footprint denominator just
    # below (same regulation, same "all investments" wording) — NOT the emissions-covered subset. An
    # earlier version of this function divided by covered_mv (renormalizing over known data only), which
    # matched PAI 2/8/9's OLD bug before those were fixed, but was never corrected here for PAI 3 — found by
    # adversarial review, re-verified against the primary text, and fixed to match every other indicator in
    # this function. numerator sums all three GHG scopes per Annex I Table 1; total_mv is the whole fund.
    # E76: an investee enters an indicator only when it states every scope that indicator sums — a missing scope 2
    # or 3 is never read as 0; the share of value each indicator covers is disclosed with it.
    def _states(r, scopes):
        return all(r[s] is not None for s in scopes)
    waci_rows = [r for r in with_emissions if _states(r, ("s1", "s2", "s3"))]
    waci_s12_rows = [r for r in with_emissions if _states(r, ("s1", "s2"))]
    waci = waci_s12 = None
    if total_mv and waci_rows:
        waci = sum(r["mv"] * ((r["s1"] + r["s2"] + r["s3"]) / (r["revenue_eur"] / 1e6)) for r in waci_rows) / total_mv
    if total_mv and waci_s12_rows:
        # the same on Scope 1+2 only — the European ESG Template asks for both (EET 30300 / 30340)
        waci_s12 = sum(r["mv"] * ((r["s1"] + r["s2"]) / (r["revenue_eur"] / 1e6)) for r in waci_s12_rows) / total_mv

    # PAI 1 — financed emissions (PCAF): attribution factor = investment ÷ EVIC.
    # Each scope sums the investees that state it (its own coverage); the total — and PAI 2 built on it — sums only
    # investees stating all three scopes, so a total never mixes a stated scope with a missing one read as 0 (E76/E79).
    # Emissions need no revenue: revenue is the denominator of PAI 3 only.
    stating = [r for r in rows if any(r[k] is not None for k in ("s1", "s2", "s3"))]
    full = [r for r in stating if _states(r, ("s1", "s2", "s3"))]

    def _scope_sum(rs, s, w=lambda r: 1.0):
        stated = [r for r in rs if r[s] is not None]
        return (sum(w(r) * r[s] for r in stated) if stated else None), sum(r["mv"] for r in stated)
    (investee_s1, cov_s1), (investee_s2, cov_s2), (investee_s3, cov_s3) = (_scope_sum(stating, s) for s in ("s1", "s2", "s3"))
    investee_total = sum(r["s1"] + r["s2"] + r["s3"] for r in full) if full else None

    # EVIC must be strictly positive; the attribution factor (investment ÷ EVIC)
    # is capped at 1.0 — you cannot finance more than 100% of an issuer, and a
    # tiny/mis-keyed EVIC would otherwise inflate financed emissions arbitrarily.
    with_evic = [r for r in stating if r.get("evic_eur") and r["evic_eur"] > 0]
    def _af(r):
        return min(r["mv"] / r["evic_eur"], 1.0)   # attribution factor, capped at 100%
    (fin_s1, fcov_s1), (fin_s2, fcov_s2), (fin_s3, fcov_s3) = (_scope_sum(with_evic, s, _af) for s in ("s1", "s2", "s3"))
    full_evic = [r for r in with_evic if _states(r, ("s1", "s2", "s3"))]
    financed_mv = sum(r["mv"] for r in full_evic)      # the value the financed total (and PAI 2) covers
    financed_total = sum(_af(r) * (r["s1"] + r["s2"] + r["s3"]) for r in full_evic) if full_evic else None
    has_financed = bool(with_evic)
    # PAI 2 — carbon footprint = financed emissions ÷ €M invested. Annex I Table 1's
    # denominator is the current value of ALL investments (total fund AUM), not just
    # the covered subset — a fund with incomplete coverage must not have its
    # intensity inflated by excluding the uncovered value from the denominator.
    # financed_emissions_coverage_pct (EVIC and all three scopes) is disclosed alongside.
    carbon_footprint = round(financed_total / (total_mv / 1e6), 1) if financed_total is not None else None

    # PAI 4 — fossil-fuel-sector exposure %. Coverage = share of value whose NACE
    # is known; a NULL-NACE holding is NOT silently treated as non-fossil in the
    # coverage claim (the % is over the whole book, coverage is disclosed separately).
    nace_known_mv = sum(r["mv"] for r in rows if r["nace_code"])
    pai4_coverage = round(100 * nace_known_mv / total_mv, 1) if total_mv else 0.0
    fossil_mv = sum(r["mv"] for r in rows if _is_fossil_fuel_nace(r["nace_code"]))

    return {
        "total_value_eur": round(total_mv),
        # Honest, disclosed schema limitation (found via the ESAs' consolidated SFDR Q&A, JC 2023 18,
        # Section III.2: for asset managers, "all investments" for the PAI 2/3/15 denominators means ALL
        # AUM — "both collective and individual portfolio management activities" — including cash, deposits
        # and derivative instruments, not just issuer-linked securities). `fund_positions` currently has no
        # way to represent a cash/deposit/derivative position at all (every row requires an issuer-linked
        # `security_id`), so total_mv/total_value_eur here reflect issuer-linked holdings ONLY. If a fund
        # holds material cash or derivative sleeves, every PAI ratio below is computed over a SMALLER
        # denominator than the true "all investments" figure the RTS defines — which INFLATES the reported
        # ratios (carbon footprint, WACI, fossil-fuel %, etc.), never understates them. This is a real,
        # acknowledged data-model gap (adding true cash/derivative position modelling is a product-design
        # task, not a quick fix) — disclosed here rather than silently assumed away.
        "denominator_scope_note": (
            "total_value_eur (and every PAI ratio's denominator) covers issuer-linked securities only — "
            "this platform cannot yet represent cash, deposits, or derivative positions as fund holdings. "
            "Per ESAs SFDR Q&A (JC 2023 18, III.2), 'all investments' should include those too; if this fund "
            "holds material cash/derivative sleeves, the ratios below are computed over a smaller-than-"
            "correct denominator, which inflates them."),
        "positions": len(rows),
        "emissions_coverage_pct": round(100 * covered_mv / total_mv, 1),
        "emissions_estimated_pct": round(100 * estimated_mv / covered_mv, 1) if covered_mv else 0.0,
        "pcaf_data_quality_score": pcaf_dq,   # PCAF 1(best)–5(worst), value-weighted over covered
        "financed_emissions_coverage_pct": round(100 * financed_mv / total_mv, 1) if total_mv else 0.0,
        "pai": {
            "pai_3_waci_tco2e_per_meur": round(waci, 1) if waci is not None else None,
            "pai_3_waci_s12_tco2e_per_meur": round(waci_s12, 1) if waci_s12 is not None else None,
            # share of value whose investees state every scope the indicator sums (and revenue)
            "pai_3_coverage_pct": round(100 * sum(r["mv"] for r in waci_rows) / total_mv, 1),
            "pai_3_s12_coverage_pct": round(100 * sum(r["mv"] for r in waci_s12_rows) / total_mv, 1),
            "pai_4_fossil_fuel_exposure_pct": round(100 * fossil_mv / total_mv, 2),
            "pai_4_coverage_pct": pai4_coverage,   # share of value whose NACE is known
            # PAI 1 — financed emissions, attributed via EVIC where available.
            "pai_1_financed_emissions_tco2e": {
                "scope_1": _r(fin_s1), "scope_2": _r(fin_s2), "scope_3": _r(fin_s3), "total": _r(financed_total),
                # share of value with EVIC whose investees state each scope; the total covers those stating all three
                "coverage_pct": {k: round(100 * c / total_mv, 1) for k, c in (("scope_1", fcov_s1), ("scope_2", fcov_s2),
                                                                              ("scope_3", fcov_s3), ("total", financed_mv))},
            } if has_financed else None,
            # PAI 2 — carbon footprint (financed emissions per €M invested).
            "pai_2_carbon_footprint_tco2e_per_meur": carbon_footprint,
            "pai_1_investee_emissions_tco2e": {
                "scope_1": _r(investee_s1), "scope_2": _r(investee_s2), "scope_3": _r(investee_s3),
                "total": _r(investee_total),
                # share of value whose investees state each scope — a scope not stated is not counted as 0 (E76);
                # the total covers investees stating all three
                "coverage_pct": {k: round(100 * c / total_mv, 1) for k, c in (("scope_1", cov_s1), ("scope_2", cov_s2),
                                                                              ("scope_3", cov_s3),
                                                                              ("total", sum(r["mv"] for r in full)))},
                "note": None if has_financed and financed_mv >= sum(r["mv"] for r in full) else
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


def fund_base_view(session, base_currency: str | None, as_of, amounts_eur: dict) -> dict:
    """A fund's values in its own base currency (multi-currency phase 4, 2026-09-27) — the figures a fund reports in —
    at the closing rate on the holdings date. Holdings are stored in EUR (converted from what was sent); SFDR PAI
    metrics stay in EUR as RTS (EU) 2022/1288 defines them (tCO2e per €M), so this is only the fund-value view."""
    from services.reference.fx import FxError, rate_for
    ccy = (base_currency or "EUR").strip().upper()
    if ccy == "EUR":
        return {"currency": "EUR", "as_of": str(as_of), **{k: None if v is None else round(v) for k, v in amounts_eur.items()}}
    try:
        r = rate_for(session, ccy, as_of)
    except FxError as e:
        return {"currency": ccy, "as_of": str(as_of), "available": False, "reason": str(e)}
    return {"currency": ccy, "as_of": str(as_of), "rate": {k: r.get(k) for k in ("units_per_eur", "rate_date", "source", "stale")},
            **{k: None if v is None else round(v * r["units_per_eur"]) for k, v in amounts_eur.items()}}


def fund_climate_summary(session, org_id: str, method, fund_id: str, scenario: str, horizon: str) -> dict:
    """Value-weighted physical + transition exposure for a fund, plus the PAI block — the one call a fund's climate
    report is built from. 'At risk' is the manager's stated method: physical — the headline score at or above its
    stated level; transition — market value × its stated stranded share. A missing parameter is a named gap."""
    from services.money.params import at_risk
    fund = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.fund_type, f.sfdr_classification, f.base_currency,
               o.name AS org_name
        FROM funds f JOIN organizations o ON o.org_id = f.org_id
        WHERE f.fund_id = :f
    """), {"f": fund_id}).mappings().first()
    if not fund:
        return {"error": "fund not found"}

    fund_ids = fund_descendant_ids(session, fund_id)
    positions = session.execute(text("""
        SELECT p.security_id::text AS security_id, CAST(p.market_value_eur AS FLOAT) AS mv, p.as_of_date,
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
    trans = issuer_transition(session, org_id, method, scenario, horizon, issuer_ids)

    # value-weighted physical; at risk = headline at or above the stated level
    phys_scored = [(p, phys[p["issuer_id"]]) for p in positions
                   if phys.get(p["issuer_id"], {}).get("headline_score") is not None]
    phys_cov_mv = sum(p["mv"] for p, _ in phys_scored)
    phys_was = (sum(p["mv"] * ph["headline_score"] for p, ph in phys_scored) / phys_cov_mv) if phys_cov_mv else None
    flags = [at_risk(method, ph["headline_score"]) for _, ph in phys_scored]
    phys_risk_mv = None if None in flags else sum(p["mv"] for (p, _), f in zip(phys_scored, flags) if f)

    # value-weighted transition score (issuers with one) and transition value at risk (Σ value × stated stranded share)
    trans_scored = [(p, trans[p["issuer_id"]]) for p in positions if trans.get(p["issuer_id"], {}).get("transition_risk_score") is not None]
    trans_cov_mv = sum(p["mv"] for p, _ in trans_scored)
    trans_was = (sum(p["mv"] * t["transition_risk_score"] for p, t in trans_scored) / trans_cov_mv) if trans_cov_mv else None
    shares = [trans.get(p["issuer_id"], {}).get("stranded_asset_pct") for p in positions]
    trans_risk_mv = None if None in shares else sum(p["mv"] * s / 100 for p, s in zip(positions, shares))
    gap = method.gap_text()          # every engine records what it asked for and did not find on the one Method

    base = fund_base_view(session, fund["base_currency"], max(p["as_of_date"] for p in positions),
                          {"total_value": total_mv, "physical_value_at_risk": phys_risk_mv,
                           "transition_value_at_risk": trans_risk_mv})
    return {
        "fund": dict(fund), "scenario": scenario, "horizon": horizon,
        "total_value_eur": round(total_mv), "positions": len(positions), "base": base,
        "physical": {
            "value_weighted_score": round(phys_was, 1) if phys_was is not None else None,
            "coverage_pct": round(100 * phys_cov_mv / total_mv, 1),
            "value_at_risk_eur": None if phys_risk_mv is None else round(phys_risk_mv),
            "pct_at_risk": None if phys_risk_mv is None else round(100 * phys_risk_mv / total_mv, 1),
        },
        "transition": {
            "value_weighted_score": round(trans_was, 1) if trans_was is not None else None,
            "coverage_pct": round(100 * trans_cov_mv / total_mv, 1),
            "value_at_risk_eur": None if trans_risk_mv is None else round(trans_risk_mv),
            "pct_at_risk": None if trans_risk_mv is None else round(100 * trans_risk_mv / total_mv, 1),
        },
        **({"gap": gap} if gap else {}),
        "pai": fund_pai(session, fund_id),
    }


