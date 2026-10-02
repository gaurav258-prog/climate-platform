"""SFDR Principal Adverse Impact (PAI) statement — the filing artifact.

This turns a fund's computed climate data into the actual document an EU asset
manager files: the mandatory PAI statement in the shape the regulation defines
(SFDR RTS — Commission Delegated Regulation (EU) 2022/1288, Annex I, Table 1),
plus the EU Taxonomy alignment lines.

The point of the whole product is that this is FILING-READY and AUDITABLE, so
the design rule is strict: every mandatory indicator is listed; the ones we can
honestly compute are filled in with their coverage and data source; the ones we
cannot are marked "not available" with the exact input still required. We never
invent a number, and we never silently drop a mandatory row — a regulator and an
auditor must see both what we have and what is missing.

What is computed today (from services/fund_disclosure.fund_pai + fund_esg_pai,
via _mandatory_indicator_rows):
    * PAI 1  — GHG emissions, financed where EVIC is available, else the
               un-attributed investee total                — computed / partial
    * PAI 2  — carbon footprint (financed emissions / €M invested, over the
               fund's total value)                          — computed / partial
    * PAI 3  — GHG intensity of investees (WACI, Scope 1+2+3) — fully computable,
               no gaps
    * PAI 4  — fossil-fuel-sector exposure                  — computed
    * PAI 5-14 — the non-carbon indicators (energy mix, energy intensity by
               high-impact NACE sector, biodiversity, water, waste, UNGC/OECD
               conduct, pay gap, board diversity, controversial weapons) — each
               computed WHERE the manager's ESG feed (issuer_esg_metrics) supplies
               that datum for a holding; value-weighted (or exposure-share, or
               EVIC-attributed, per indicator shape) over the covered value.
Any indicator — including 5-14 — for which no manager has supplied the underlying
issuer datum is surfaced as an explicit "not available" gap with the exact input
still required, never a silent zero.

Scope: investee-company indicators (equity / corporate-bond funds), which is the
beachhead. Sovereign (Table 1, indicators 15-16) and real-estate (17-18) tables
are out of scope for this first version and flagged as such.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

from sqlalchemy import text

from ml.regulatory.voluntary_pai import compute_voluntary_pai
from services.asset_manager_engine import fund_descendant_ids
from services.fund_disclosure import fund_esg_pai, fund_pai

# ── The mandatory PAI indicators (SFDR RTS Annex I, Table 1 — investee companies) ──
# Each: number, area, metric (as worded by the RTS), unit. Value/coverage/source
# are filled per-fund at assembly time.
MANDATORY_PAI_INDICATORS = [
    (1,  "Climate & environment", "GHG emissions (Scope 1, 2 and 3, and total)", "tCO₂e"),
    (2,  "Climate & environment", "Carbon footprint (financed emissions per €M invested)", "tCO₂e/€M"),
    (3,  "Climate & environment", "GHG intensity of investee companies (WACI)", "tCO₂e/€M revenue"),
    (4,  "Climate & environment", "Exposure to companies active in the fossil fuel sector", "% of value"),
    (5,  "Climate & environment", "Share of non-renewable energy consumption and production", "%"),
    (6,  "Climate & environment", "Energy consumption intensity per high-impact climate sector", "GWh/€M revenue"),
    (7,  "Biodiversity",          "Activities negatively affecting biodiversity-sensitive areas", "% of value"),
    (8,  "Water",                 "Emissions to water", "tonnes/€M invested"),
    (9,  "Waste",                 "Hazardous waste and radioactive waste ratio", "tonnes/€M invested"),
    (10, "Social & governance",   "Violations of UN Global Compact / OECD Guidelines", "% of value"),
    (11, "Social & governance",   "Lack of processes to monitor UNGC / OECD compliance", "% of value"),
    (12, "Social & governance",   "Unadjusted gender pay gap", "%"),
    (13, "Social & governance",   "Board gender diversity", "% female"),
    (14, "Social & governance",   "Exposure to controversial weapons", "% of value"),
]

# ── Earlier answers not tied to any reference period: five free-text boxes, one set for every period (family 'sfdr_pai',
# document 'pai_statement', no period_end). The statement is now answered per reference period, item by item as Articles
# 5 to 9 require (services.governance.sfdr_pai_answers); these are only shown, for reference, never filed or edited.
NARRATIVE_FAMILY, NARRATIVE_DOCUMENT = "sfdr_pai", "pai_statement"


def entity_narratives(session, org_id: str) -> dict:
    """{section: text} of the earlier answers not tied to a period (read-only)."""
    from services.governance import template_answers as T
    return {k: v["text"] for k, v in T.read(session, org_id, NARRATIVE_FAMILY, NARRATIVE_DOCUMENT).items() if v.get("text")}


_GOLDEN_SOURCE = "Tellumen golden source (issuer emissions + revenue, provenance-stamped)"

# ── Sovereign PAI (RTS Annex I, Table 1, indicators 15-16) ──
# GHG intensity of investee COUNTRIES: tCO2e per €M GDP — the RTS basis: total GHG (CO2e, excl. LULUCF; national
# inventory, else EDGAR) ÷ GDP at
# current market prices in EUR, same year. Loaded from data/reference/country_ghg_intensity.csv (built by
# scripts/build_country_intensities.py, every input kept per row); the embedded dict is the offline fallback.
# Until 2026-09-27 the file divided CO2 only by PPP GDP (constant international $) — not the RTS basis.
_EMBEDDED_COUNTRY_INTENSITY: dict[str, float] = {
    "SE": 50, "CH": 59, "NO": 70, "FR": 90, "GB": 110, "IT": 120, "DK": 95,
    "ES": 130, "AT": 154, "PT": 130, "FI": 110, "NL": 140, "IE": 90, "BE": 182,
    "DE": 172, "GR": 150, "US": 200, "JP": 160, "PL": 350, "CZ": 277, "IN": 600,
    "CN": 421, "ZA": 700, "RU": 550, "AU": 286, "BR": 152, "CA": 313,
}
DEFAULT_COUNTRY_INTENSITY = 200.0     # kept for reference only — a country with no figure is NOT given it (see below)


def _load_country_intensity() -> dict[str, float]:
    import csv as _csv
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent.parent / "data" / "reference" / "country_ghg_intensity.csv"
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            table = {r["country_iso2"].strip().upper(): float(r["intensity_tco2e_per_meur"])
                     for r in _csv.DictReader(fh) if r.get("country_iso2")}
        if table:
            return table
    except (OSError, KeyError, ValueError):
        pass
    return dict(_EMBEDDED_COUNTRY_INTENSITY)


COUNTRY_GHG_INTENSITY_TCO2E_PER_MEUR = _load_country_intensity()


def _country_vintage() -> str:
    """The GDP/GHG year(s) of the country table, as read from the file (never a hard-coded year)."""
    import csv as _csv
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent.parent / "data" / "reference" / "country_ghg_intensity.csv"
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            years = sorted({r["gdp_year"] for r in _csv.DictReader(fh) if r.get("gdp_year")})
    except (OSError, KeyError):
        return "n/a"
    return years[-1] if len(years) == 1 else (f"{years[0]}–{years[-1]}" if years else "n/a")

SOVEREIGN_ASSET_CLASSES = ("sovereign_bond",)
REAL_ESTATE_ASSET_CLASSES = ("real_estate",)  # not in the securities model today


def _pai_basis() -> str:
    """Where the PAI statement template sits in the regulation that governs today (its specification)."""
    import services.regspec as R
    spec = R.governing("sfdr_pai", period_end=datetime.now(timezone.utc).date())
    return R.citation(spec, "T1") if spec else "SFDR RTS, Annex I, Table 1"


def _row(num, area, metric, unit, *, value=None, coverage=None, source=None,
         method="not_available", input_required=None):
    """One indicator line. method ∈ computed / partial / estimated / not_available."""
    return {
        "number": num, "area": area, "metric": metric, "unit": unit,
        "value": value, "coverage_pct": coverage, "source": source,
        "method": method, "input_required": input_required,
    }


def _taxonomy_rollup(session, fund_id: str, *, fund_ids=None, org_id=None, as_of=None) -> dict:
    """EU Taxonomy lines for the fund, honestly scoped.

    Eligibility can only be judged where we hold the issuer's NACE code; alignment
    is never asserted (DNSH across the six objectives + minimum safeguards are not
    verified) — matching the classifier's discipline. We report the share of value
    we can even assess, so the gap is explicit.

    Annex III §1.2 of Del. Reg. (EU) 2021/2178 (verified verbatim against the Official Journal text: "Asset
    managers shall disclose a KPI based on turnover KPIs of the investee companies and a KPI based on the
    CapEx KPI of investee companies") requires TWO separate Taxonomy-aligned KPIs shown side by side —
    turnover-based and CapEx-based — never blended into one figure. (Annex IV is the accompanying template,
    not a second normative source — the requirement itself is entirely in Annex III.)
    The investee's turnover-based KPI and its CapEx-based companion come from the one store of
    issuer Taxonomy KPIs (services.issuer_taxonomy). Both
    are value-weighted the same way, over the same DNSH/minimum-safeguards gate,
    each independently disclosing its own coverage — a fund can have full turnover
    coverage and zero CapEx coverage (or vice versa), so they must not be averaged
    together or let one silently stand in for the other.
    """
    if org_id is None:
        org_id = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    if fund_ids is None:
        fund_ids = fund_descendant_ids(session, fund_id)
    rows = [dict(r) for r in session.execute(text("""
        SELECT CAST(p.market_value_eur AS FLOAT) AS mv, i.nace_code, i.issuer_id::text AS issuer_id
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        JOIN   issuers   i ON i.issuer_id = s.issuer_id
        WHERE  p.fund_id = ANY(:fids)
          AND  p.as_of_date = COALESCE(CAST(:as_of AS date), (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id))
    """), {"fids": fund_ids, "as_of": as_of}).mappings().all()]
    # the investee's own KPIs and the DNSH / safeguards gate, from the one store (services.issuer_taxonomy)
    from services.issuer_taxonomy import gate_failures
    from services.issuer_taxonomy import kpis as investee_kpis
    ids = sorted({r["issuer_id"] for r in rows})
    year = None if as_of is None else int(str(as_of)[:4])      # a statement's date: figures for that year or earlier
    k, failing = investee_kpis(session, org_id, ids, year), gate_failures(session, org_id, ids, year)
    for r in rows:
        t, c = (k.get(r["issuer_id"]) or {}).get("turnover") or {}, (k.get(r["issuer_id"]) or {}).get("capex") or {}
        r.update(elig=t.get("eligible"), aligned=t.get("aligned"), aligned_capex=c.get("aligned"),
                 gate_failed=r["issuer_id"] in failing)
    total = sum(r["mv"] for r in rows) or 0.0
    with_nace = sum(r["mv"] for r in rows if r["nace_code"])
    # Value-weighted alignment/eligibility over holdings that supplied the issuer's
    # own Article-8 figure — coverage disclosed; alignment ONLY from reported data.
    # DNSH gate: an issuer whose DNSH or minimum-safeguards attestation is explicitly
    # FALSE cannot count as aligned (a known controversy overrides the reported %).
    # A NULL flag means "not separately assessed" → the reported figure stands.
    def _dnsh_fail(r):
        return r["gate_failed"]

    def _kpi(field: str) -> dict:
        """One Taxonomy-aligned KPI (turnover or capex), value-weighted with the
        same DNSH gate, independently coverage-disclosed."""
        cov = [(r["mv"], r[field]) for r in rows if r[field] is not None and not _dnsh_fail(r)]
        excluded = [(r["mv"], r[field]) for r in rows if r[field] is not None and _dnsh_fail(r)]
        w = sum(mv for mv, _ in cov)
        excl_w = sum(mv for mv, _ in excluded)
        return {
            "aligned_pct": round(sum(mv * v for mv, v in cov) / total, 1) if w else None,
            "coverage_pct": round(100 * w / total, 1) if total else 0.0,
            "excluded_dnsh_pct": round(100 * excl_w / total, 1) if excl_w else 0.0,
            "input_required": None if w else "per-issuer reported Taxonomy-aligned % (Article 8 disclosures)",
        }

    elig_cov = [(r["mv"], r["elig"]) for r in rows if r["elig"] is not None]
    elig_w = sum(mv for mv, _ in elig_cov)
    turnover = _kpi("aligned")
    capex = _kpi("aligned_capex")

    def _note(kpi: dict, label: str) -> str:
        if kpi["aligned_pct"] is None and not kpi["excluded_dnsh_pct"]:
            return (f"{label} alignment not asserted: no issuer has supplied its reported {label}-based "
                    f"Taxonomy-aligned %. Supply per-issuer Article-8 {label.lower()} figures to populate this.")
        return (
            f"{label} aligned % is value-weighted over the {kpi['coverage_pct']}% of the book whose issuers "
            f"reported an Article-8 {label}-based Taxonomy-aligned figure and passed the DNSH / minimum-"
            "safeguards gate. "
            + (f"A further {kpi['excluded_dnsh_pct']}% reported aligned {label.lower()} but was EXCLUDED "
               "because its DNSH or minimum-safeguards attestation is flagged as failing. " if kpi["excluded_dnsh_pct"] else "")
            + "Where no figure is reported, no alignment is asserted (eligible-at-most) — we never infer "
            "DNSH or minimum-safeguards ourselves.")

    return {
        "assessable_pct": round(100 * with_nace / total, 1) if total else 0.0,
        "taxonomy_eligible_pct": round(sum(mv * v for mv, v in elig_cov) / total, 1) if elig_w else None,
        # ── DEPRECATED (ambiguous name, kept for every existing caller — see
        # taxonomy_aligned_turnover_pct for the same value under its honest name) ──
        "taxonomy_aligned_pct": turnover["aligned_pct"],
        "alignment_coverage_pct": turnover["coverage_pct"],
        "aligned_excluded_dnsh_pct": turnover["excluded_dnsh_pct"],
        "alignment_note": _note(turnover, "Turnover"),
        "input_required": turnover["input_required"],
        # ── The dual Taxonomy KPI (Annex III/IV of Del. Reg. (EU) 2021/2178) —
        # turnover-based and CapEx-based, always shown and computed separately ──
        "taxonomy_aligned_turnover_pct": turnover["aligned_pct"],
        "turnover_alignment_coverage_pct": turnover["coverage_pct"],
        "turnover_aligned_excluded_dnsh_pct": turnover["excluded_dnsh_pct"],
        "turnover_alignment_note": _note(turnover, "Turnover"),
        "taxonomy_aligned_capex_pct": capex["aligned_pct"],
        "capex_alignment_coverage_pct": capex["coverage_pct"],
        "capex_aligned_excluded_dnsh_pct": capex["excluded_dnsh_pct"],
        "capex_alignment_note": _note(capex, "CapEx"),
        "capex_input_required": capex["input_required"],
    }


def _composition_and_sovereign(session, fund_id: str, *, fund_ids=None, org_id=None, as_of=None) -> dict:
    """Fund value by asset class + a value-weighted sovereign GHG intensity over
    any sovereign-bond holdings (their issuer's country → country intensity)."""
    if fund_ids is None:
        fund_ids = fund_descendant_ids(session, fund_id)
    rows = session.execute(text("""
        SELECT s.asset_class, i.country, CAST(p.market_value_eur AS FLOAT) AS mv
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        JOIN   issuers    i ON i.issuer_id = s.issuer_id
        WHERE  p.fund_id = ANY(:fids)
          AND  p.as_of_date = COALESCE(CAST(:as_of AS date), (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id))
    """), {"fids": fund_ids, "as_of": as_of}).mappings().all()
    by_class: dict[str, float] = {}
    sov_mv = covered_mv = 0.0
    sov_weighted_intensity = 0.0
    sov_countries: set = set()
    uncovered: set = set()
    for r in rows:
        by_class[r["asset_class"]] = by_class.get(r["asset_class"], 0.0) + r["mv"]
        if r["asset_class"] in SOVEREIGN_ASSET_CLASSES:
            sov_mv += r["mv"]
            ctry = (r["country"] or "").upper()
            intensity = COUNTRY_GHG_INTENSITY_TCO2E_PER_MEUR.get(ctry)
            if intensity is None:                 # no figure for this country: left out and reported, never a default
                uncovered.add(ctry or "unknown")
            else:
                covered_mv += r["mv"]
                sov_weighted_intensity += r["mv"] * intensity
            if ctry:
                sov_countries.add(ctry)
    return {
        "by_asset_class": {k: round(v) for k, v in by_class.items()},
        "sovereign_value_eur": round(sov_mv),
        "sovereign_ghg_intensity": round(sov_weighted_intensity / covered_mv, 1) if covered_mv else None,
        "sovereign_coverage_pct": round(100 * covered_mv / sov_mv, 1) if sov_mv else None,
        "sovereign_uncovered_countries": sorted(uncovered),
        "sovereign_countries": sorted(sov_countries),
        "has_real_estate": any(c in REAL_ESTATE_ASSET_CLASSES for c in by_class),
    }


def _sovereign_indicators(comp: dict) -> list[dict]:
    """RTS Annex I Table 1 indicators 15-16 (sovereign & supranational)."""
    si = comp["sovereign_ghg_intensity"]
    cov = comp.get("sovereign_coverage_pct", 100.0 if si is not None else None)
    missing = comp.get("sovereign_uncovered_countries") or []
    return [
        _row(15, "Sovereign", "GHG intensity of investee countries", "tCO₂e/€M GDP",
             value=si, coverage=cov,
             source=("country total GHG excl. LULUCF ÷ GDP at current prices in EUR, same year (national inventory where "
                     "Eurostat carries it, else EC-JRC EDGAR; World Bank WDI; ECB)") if si is not None else None,
             method=("partial" if missing else "computed") if si is not None else "not_available",
             input_required=(f"GHG intensity for {', '.join(missing)} (no public figure — excluded from the average)"
                             if missing else None) if si is not None else "sovereign-bond holdings with issuer country"),
        _row(16, "Sovereign", "Investee countries subject to social violations", "count",
             method="not_available",
             input_required="country social-violation list (UN/OECD sanctions & breaches)"),
    ]


def _real_estate_indicators(comp: dict) -> list[dict]:
    """RTS Annex I Table 1 indicators 17-18 (real-estate assets)."""
    applic = "applies to direct real-estate assets; this fund holds securities, not property" \
        if not comp["has_real_estate"] else None
    method = "not_applicable" if not comp["has_real_estate"] else "not_available"
    return [
        _row(17, "Real estate", "Exposure to fossil fuels through real-estate assets", "% of RE value",
             method=method, input_required=applic or "real-estate asset fossil-fuel involvement"),
        _row(18, "Real estate", "Exposure to energy-inefficient real-estate assets", "% of RE value",
             method=method, input_required=applic or "real-estate asset EPC ratings"),
    ]


def _indicator_numeric(value):
    """Reduce an indicator value to a comparable scalar (dict → its 'total')."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and isinstance(value.get("total"), (int, float)):
        return float(value["total"])
    return None


def _attach_prior_year(session, fund_id: str, ref_year, indicators: list[dict]) -> dict:
    """Look up the most recent FILED snapshot for a prior year and attach each
    indicator's prior value + change. Returns comparison metadata. If none exists
    (first reference period), indicators are left as-is."""
    if not ref_year:
        return {"available": False, "reason": "no reference year on the current statement"}
    row = session.execute(text("""
        SELECT reference_year, statement FROM fund_sfdr_filings
        WHERE fund_id = :f AND reference_year < :y AND status = 'filed'
        ORDER BY reference_year DESC LIMIT 1
    """), {"f": fund_id, "y": ref_year}).mappings().first()
    if not row:
        return {"available": False, "reason": "first reference period — no prior filing to compare"}

    prior_by_num = {i["number"]: i for i in (row["statement"].get("indicators") or [])}
    for ind in indicators:
        prior = prior_by_num.get(ind["number"])
        if not prior:
            continue
        ind["prior_value"] = prior.get("value")
        # Only compute a change when the two periods are LIKE-FOR-LIKE. PAI 1's
        # value shape changes with method (un-attributed investee total vs
        # PCAF-attributed financed total) — comparing across those would fabricate
        # a huge bogus move, so a method mismatch shows the prior value but no change.
        if prior.get("method") != ind.get("method"):
            ind["change_note"] = _basis_change_note(prior, ind)
            continue
        pv, cv = _indicator_numeric(prior.get("value")), _indicator_numeric(ind.get("value"))
        if pv is not None and cv is not None:
            ind["change"] = round(cv - pv, 3)
            ind["change_pct"] = round(100 * (cv - pv) / pv, 1) if pv else None
    return {"available": True, "prior_reference_year": row["reference_year"]}


def _basis_change_note(prior: dict, ind: dict) -> str:
    """Plain words for a year-on-year move that is NOT like for like — carried into the RTS 'Explanation' column, so
    the reader (and the regulator) sees why the figure moved, not only that it did."""
    was, now = prior.get("method"), ind.get("method")
    pc, cc = prior.get("coverage_pct"), ind.get("coverage_pct")
    cov = f"; coverage {pc}% → {cc}%" if pc is not None and cc is not None else ""
    if now == "estimated" and was != "estimated":
        return (f"Not directly comparable with last year: this year's figure also covers holdings with no reported data, "
                f"using documented sector / country estimates{cov}. Last year's figure covered reported data only.")
    if was == "estimated" and now != "estimated":
        return f"Not directly comparable with last year: last year's figure included estimates; this year's rests on reported data{cov}."
    return f"Not directly comparable with last year: the calculation basis changed ({was} → {now}{cov})."


def _look_through(session, fund_id: str, comp: dict) -> dict:
    """Report look-through status. A held fund/ETF that has been expanded lives as
    a sub-fund (folded into the roll-up); an unexpanded one still shows as an
    etf/fund asset class and is flagged as needing its constituents."""
    expanded = session.execute(text(
        "SELECT count(*) FROM funds WHERE parent_fund_id = :f AND name LIKE '%· look-through'"
    ), {"f": fund_id}).scalar()
    held = {k: v for k, v in comp["by_asset_class"].items() if k in ("etf", "fund")}
    if held:
        return {
            "applicable": True, "held_fund_value_eur": sum(held.values()),
            "status": "not_expanded", "expanded_vehicles": expanded,
            "input_required": "constituent holdings of the held funds/ETFs (POST /funds/{id}/lookthrough)",
        }
    if expanded:
        return {"applicable": True, "status": "expanded", "expanded_vehicles": expanded,
                "note": "Held vehicles expanded to constituents; PAI reflects the underlying issuers."}
    return {"applicable": False, "note": "No held funds/ETFs — direct securities only, no look-through required."}


def _mandatory_indicator_rows(pai: dict, esg: dict):
    """Build the 14 mandatory PAI indicator rows (filled or gap-flagged) from a
    computed pai + esg block. Shared by the fund and entity-level assemblers.
    Returns (indicators, computed_count, partial_count, missing_count)."""
    p = pai["pai"]
    emis_est = pai.get("emissions_estimated_pct", 0.0)
    inv = p["pai_1_investee_emissions_tco2e"]
    fin = p.get("pai_1_financed_emissions_tco2e")

    # each row carries the coverage of exactly the investees it sums (E79): a scope over those stating it, a total and
    # PAI 2 over those stating all three scopes (with EVIC), PAI 3 over those stating all three and revenue
    def _status(value, cov, rest):
        if value is None:
            return "not_available", rest(100.0)
        return ("computed", None) if cov >= 99.9 else ("partial", rest(round(100 - cov, 1)))

    filled: dict[int, dict] = {}
    if fin:
        cov = fin["coverage_pct"]["total"]
        method, need = _status(fin["total"], cov, lambda r: f"issuer EVIC and scope 1, 2 and 3 emissions on the remaining {r}% by value")
        filled[1] = _row(1, "Climate & environment",
                         "GHG emissions — financed (Scope 1, 2, 3, total)", "tCO₂e",
                         value={"scope_1": fin["scope_1"], "scope_2": fin["scope_2"],
                                "scope_3": fin["scope_3"], "total": fin["total"]},
                         coverage=cov, source=_GOLDEN_SOURCE + " · PCAF attribution (investment ÷ EVIC)",
                         method=method, input_required=need)
        filled[1]["coverage_by_scope"] = fin["coverage_pct"]
    else:
        filled[1] = _row(1, "Climate & environment",
                         "GHG emissions (Scope 1, 2 and 3, and total)", "tCO₂e",
                         value={"scope_1": inv["scope_1"], "scope_2": inv["scope_2"],
                                "scope_3": inv["scope_3"], "total": inv.get("total")},
                         coverage=inv["coverage_pct"]["total"], source=_GOLDEN_SOURCE, method="partial",
                         input_required="issuer EVIC (enterprise value incl. cash) to attribute "
                                        "financed emissions per PCAF")
        filled[1]["coverage_by_scope"] = inv["coverage_pct"]
    cf = p.get("pai_2_carbon_footprint_tco2e_per_meur")
    cov2 = fin["coverage_pct"]["total"] if fin else 0.0
    method, need = _status(cf, cov2, lambda r: f"issuer EVIC and scope 1, 2 and 3 emissions on the remaining {r}% by value")
    filled[2] = _row(2, "Climate & environment",
                     "Carbon footprint (financed emissions per €M invested)", "tCO₂e/€M",
                     value=cf, coverage=cov2 if cf is not None else None,
                     source=_GOLDEN_SOURCE + " · PCAF" if cf is not None else None,
                     method=method, input_required=need)
    waci_src = _GOLDEN_SOURCE + (f" · {emis_est}% of covered value estimated" if emis_est else "")
    waci, cov3 = p["pai_3_waci_tco2e_per_meur"], p.get("pai_3_coverage_pct", 0.0)
    method, need = _status(waci, cov3, lambda r: f"issuer scope 1, 2 and 3 emissions and revenue on the remaining {r}% by value")
    filled[3] = _row(3, "Climate & environment",
                     "GHG intensity of investee companies (WACI)", "tCO₂e/€M revenue",
                     value=waci, coverage=cov3 if waci is not None else None,
                     source=waci_src if waci is not None else None, method=method, input_required=need)
    filled[3]["value_scope_1_2"] = p.get("pai_3_waci_s12_tco2e_per_meur")   # EET 30300 asks Scope 1+2 separately
    filled[3]["coverage_scope_1_2"] = p.get("pai_3_s12_coverage_pct")
    filled[4] = _row(4, "Climate & environment",
                     "Exposure to companies active in the fossil fuel sector", "% of value",
                     value=p["pai_4_fossil_fuel_exposure_pct"], coverage=p.get("pai_4_coverage_pct", 100.0),
                     source="issuer NACE division (golden source)",
                     method="computed" if p.get("pai_4_coverage_pct", 100.0) >= 99.9 else "partial",
                     input_required=None if p.get("pai_4_coverage_pct", 100.0) >= 99.9
                     else f"issuer NACE on the remaining {round(100 - p.get('pai_4_coverage_pct', 100.0), 1)}% by value")

    remaining_inputs = {
        5: "issuer energy mix (renewable vs non-renewable share)",
        6: "issuer energy consumption (GWh) by high-impact NACE",
        7: "issuer operations in/near biodiversity-sensitive areas",
        8: "issuer emissions to water (tonnes)",
        9: "issuer hazardous/radioactive waste (tonnes)",
        10: "UNGC/OECD violation flags per issuer",
        11: "issuer compliance-monitoring process disclosure",
        12: "issuer unadjusted gender pay gap",
        13: "issuer board gender diversity",
        14: "controversial-weapons involvement flags per issuer",
    }
    _ESG_SRC = "issuer ESG disclosures (manager feed), value-weighted"
    for num in range(5, 15):
        cell = esg.get(f"pai_{num}") if esg else None
        if cell and cell.get("value") is not None:
            est = cell.get("estimated_pct") or 0.0          # PAI 5/6: the part of the fund resting on sector/country estimates
            src = _ESG_SRC + (f" · {est}% of fund value estimated (EU sector / country averages — see provenance)" if est else "")
            filled[num] = _row(num, next(a for n, a, _, __ in MANDATORY_PAI_INDICATORS if n == num),
                               next(m for n, _, m, __ in MANDATORY_PAI_INDICATORS if n == num),
                               next(u for n, _, __, u in MANDATORY_PAI_INDICATORS if n == num),
                               value=cell["value"], coverage=cell["coverage_pct"], source=src,
                               method="estimated" if est else ("computed" if cell["coverage_pct"] >= 99.9 else "partial"),
                               input_required=None if cell["coverage_pct"] >= 99.9 and not est
                               else f"{remaining_inputs[num]} on the {round(100 - cell['coverage_pct'] + est, 1)}% by value not reported")
    if esg and 5 in filled:           # the European ESG Template asks PAI 5 split, and PAI 6 per high-impact section
        filled[5]["consumption"], filled[5]["production"] = esg.get("pai_5_consumption"), esg.get("pai_5_production")
    if esg and 6 in filled:
        filled[6]["by_section"] = esg.get("pai_6_by_section")

    indicators = []
    for num, area, metric, unit in MANDATORY_PAI_INDICATORS:
        if num in filled:
            indicators.append(filled[num])
        else:
            indicators.append(_row(num, area, metric, unit, input_required=remaining_inputs.get(num)))

    computed = sum(1 for i in indicators if i["method"] == "computed")
    partial = sum(1 for i in indicators if i["method"] == "partial")
    missing = sum(1 for i in indicators if i["method"] == "not_available")
    return indicators, computed, partial, missing


def sfdr_pai_statement(session, fund_id: str) -> dict:
    """Assemble the fund's full SFDR PAI statement (Annex I Table 1) + Taxonomy.

    Returns a structured, filing-shaped dict: entity metadata, the 14 mandatory
    indicators (filled or gap-flagged), Taxonomy lines, a coverage summary, and
    provenance. Raises nothing for missing data — it is disclosed, not hidden.
    """
    fund = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.sfdr_classification, f.base_currency, f.lei AS fund_lei,
               o.name AS org_name, o.lei AS manager_lei, o.legal_name AS manager_legal_name,
               o.filing_contact_email, o.country AS manager_domicile, o.org_id::text AS org_id
        FROM funds f JOIN organizations o ON o.org_id = f.org_id
        WHERE f.fund_id = :f
    """), {"f": fund_id}).mappings().first()
    if not fund:
        return {"error": "fund not found"}

    pai = fund_pai(session, fund_id)
    if pai.get("positions", 0) == 0:
        return {"error": "fund has no positions to report on", "fund": dict(fund)}

    emis_cov = pai.get("emissions_coverage_pct")
    emis_est = pai.get("emissions_estimated_pct", 0.0)  # SFDR: estimated-vs-reported split

    # PAI 5-14 — the non-carbon indicators, computed from issuer_esg_metrics where
    # the manager has supplied that ESG data (value-weighted / share / attributed).
    esg = fund_esg_pai(session, fund_id)
    indicators, computed, partial, missing = _mandatory_indicator_rows(pai, esg)

    comp = _composition_and_sovereign(session, fund_id)

    # Reference period = the vintage covering the most DISTINCT issuers across the
    # fund (and its sub-funds), scoped to this org's own disclosures + the global
    # fallback. Counting distinct issuers (not raw rows) and filtering by org means
    # another tenant's private data and per-issuer duplicate rows can't tip the year.
    org_id = session.execute(text("SELECT org_id::text FROM funds WHERE fund_id = :f"), {"f": fund_id}).scalar()
    fund_ids = fund_descendant_ids(session, fund_id)
    ref_year = session.execute(text("""
        SELECT e.reporting_year FROM fund_positions p
        JOIN securities s ON s.security_id = p.security_id
        JOIN issuer_emissions e ON e.issuer_id = s.issuer_id
        WHERE p.fund_id = ANY(:fids) AND e.scope1_tco2e IS NOT NULL
          AND (e.org_id = :org OR e.org_id IS NULL)
        GROUP BY e.reporting_year
        ORDER BY count(DISTINCT s.issuer_id) DESC, e.reporting_year DESC LIMIT 1
    """), {"fids": fund_ids, "org": org_id}).scalar()

    # Year-on-year: attach each indicator's prior filed value + change (SFDR yr 2+).
    comparison = _attach_prior_year(session, fund_id, ref_year, indicators)
    # indicators whose basis changed since the last filing — each explained in its row; listed so the preparer sees them
    comparison["basis_changes"] = [{"number": i["number"], "note": i["change_note"]} for i in indicators if i.get("change_note")]

    manager_lei = fund.get("manager_lei")
    # Filing-readiness: the reporting-entity identity SFDR's Annex I header needs.
    # NB: keep this list name distinct from the `missing` indicator COUNT above.
    filing_missing = []
    if not manager_lei:
        filing_missing.append("manager LEI")
    if not fund.get("manager_legal_name"):
        filing_missing.append("manager legal name")
    if not fund.get("filing_contact_email"):
        filing_missing.append("filing contact email")
    if not ref_year:
        filing_missing.append("reference period (supply issuer emissions with a reporting year)")
    # the sections of Articles 5 to 10 belong to the manager's entity-level statement (answered per reference period),
    # not to a fund: a fund's consideration of principal adverse impacts is disclosed in its SFDR product documents
    ready_to_file = not filing_missing

    return {
        "entity": {
            "fund_id": fund["fund_id"], "fund_name": fund["name"], "fund_lei": fund.get("fund_lei"),
            "manager": fund["org_name"], "manager_lei": manager_lei,
            "manager_legal_name": fund.get("manager_legal_name"),
            "manager_domicile": fund.get("manager_domicile"),
            "filing_contact_email": fund.get("filing_contact_email"),
            "base_currency": fund["base_currency"],
            "sfdr_classification": fund["sfdr_classification"],
            "total_value_eur": pai["total_value_eur"], "positions": pai["positions"],
        },
        # RTS Annex I header/declaration + reference period.
        "summary": {
            "reference_period": f"FY{ref_year}" if ref_year else "reference period not set (supply issuer emissions with a reporting year)",
            "reference_year": ref_year,
            "prior_period": "Not available — first reference period",
            "pai_considered": True,
            "manager_lei_required": manager_lei is None,
            "declaration": (
                f"This is the principal adverse impacts statement on sustainability factors of "
                f"{fund.get('manager_legal_name') or fund['org_name']} ({manager_lei or 'LEI required'}) for the fund "
                f"'{fund['name']}', reference period {('FY' + str(ref_year)) if ref_year else '—'}. "
                "Principal adverse impacts of investment decisions on sustainability factors are considered."
            ),
        },
        "filing_readiness": {
            "ready_to_file": ready_to_file,
            "missing": filing_missing,
            "note": "Ready to file." if ready_to_file
                    else "Not yet submittable — supply the reporting-entity identity above.",
        },
        "statement": "Principal Adverse Impact (PAI) statement",
        "regulatory_basis": _pai_basis(),
        "comparison": comparison,   # prior-period availability + year (indicators carry prior_value/change)
        "indicators": indicators,
        "holdings_composition": comp["by_asset_class"],
        # Sovereign indicators (15-16) shown only when the fund holds sovereigns.
        "sovereign_indicators": _sovereign_indicators(comp) if comp["sovereign_value_eur"] else [],
        "sovereign_countries": comp["sovereign_countries"],
        # Real-estate indicators (17-18) — always listed with their applicability.
        "real_estate_indicators": _real_estate_indicators(comp),
        "taxonomy": _taxonomy_rollup(session, fund_id),
        # Additional (voluntary) PAI — SFDR requires the manager to adopt ≥1 more
        # climate and ≥1 more social indicator from RTS Tables 2 & 3. The manager
        # selects which; we compute the roll-up over supplied issuer values.
        "additional_indicators": compute_voluntary_pai(session, fund_id, comp),
        # Look-through — if the book holds funds/ETFs, their constituents must be
        # looked through. Detected from asset_class; honest status, not faked.
        "look_through": _look_through(session, fund_id, comp),
        "coverage_summary": {
            "mandatory_indicators": len(indicators),
            "computed": computed, "partial": partial, "not_available": missing,
            "emissions_coverage_pct": emis_cov,
            "emissions_estimated_pct": emis_est,   # of covered value, the reported/estimated split (SFDR RTS)
            "pcaf_data_quality_score": pai.get("pcaf_data_quality_score"),  # PCAF 1(best)–5(worst)
            "filing_readiness": (
                f"{computed} of {len(indicators)} mandatory indicators computed, "
                f"{partial} partial, {missing} awaiting issuer input. This statement is "
                "structurally complete and audit-traceable; the gaps are disclosed as "
                "required inputs, not estimated or omitted."
            ),
        },
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": _GOLDEN_SOURCE,
            "scope_note": "Investee-company + sovereign + real-estate indicators, per the "
                          "holdings actually present. Scope 3 emissions are not estimated.",
            "data_sources": [
                {"item": "Issuer identity & ISIN→LEI", "source": "GLEIF (open LEI system)", "vintage": "resolved at onboarding"},
                {"item": "Facility location", "source": "GLEIF HQ address → OpenStreetMap/Nominatim geocode", "vintage": "at onboarding"},
                {"item": "Physical hazard scores", "source": "Tellumen golden source (canonical_scores, append-only)", "vintage": "model-stamped"},
                {"item": "Issuer emissions / revenue / EVIC", "source": "client disclosure where supplied; else estimated", "vintage": f"FY{ref_year}" if ref_year else "n/a"},
                {"item": "Estimated emissions", "source": "NACE sector intensity × revenue — EXIOBASE 3 IOT_2022_ixi (EU output-weighted GHG), interim fallback where EXIOBASE folds sectors", "vintage": "2022"},
                {"item": "Estimated energy intensity (PAI 6)", "source": "EU-27 energy consumed per €M turnover by NACE activity — Eurostat energy accounts (PEFA) ÷ structural business statistics (data/reference/nace_energy_intensity.csv); only where no company or vendor figure", "vintage": "2022"},
                {"item": "Estimated energy mix (PAI 5)", "source": "country renewable share of primary energy (consumption) / of electricity (producers) — Our World in Data (data/reference/country_renewable_shares.csv); only where no company or vendor figure", "vintage": "2024"},
                {"item": "Sovereign country GHG intensity", "source": "total GHG excl. LULUCF — the country's national inventory (UNFCCC, via Eurostat) where available, else EC-JRC EDGAR (all gases, GWP-100 AR5) — ÷ GDP at current prices in EUR (World Bank WDI × ECB annual average), same year (data/reference/country_ghg_intensity.csv)", "vintage": _country_vintage()},
            ],
            "model_versions": {
                "emissions_estimation": "emissions-est-v1-sector-intensity",
                "attribution": "PCAF: investment ÷ EVIC",
            },
            "disclosures": {
                "emissions_coverage_pct": emis_cov,
                "emissions_estimated_pct": emis_est,
                "financed_emissions_coverage_pct": pai.get("financed_emissions_coverage_pct", 0.0),
            },
            "manager_actions_note": "Actions taken and targets (RTS Table 1, final columns) are a "
                                    "manager narrative and must be completed by the manager; not machine-derived.",
        },
    }


def frozen_or_live_statement(session, fund_id: str) -> tuple[dict, bool]:
    """The statement to actually EXPORT/download for this fund: the FROZEN, filed record for its current
    reference year if one exists — never a live recompute — else the live draft.

    Fixed 2026-09-24 (independent platform-wide E2E audit): sfdr_statement_xlsx/.xbrl/.ixbrl in
    api/routers/funds.py used to call sfdr_pai_statement() directly on every single request, even for an
    already-FILED fund. Proved live: froze a statement (WACI=292.0), made one further look-through change,
    re-downloaded the SAME export endpoint, and got a DIFFERENT number (WACI=179.9) — an attested/filed
    export silently drifting from what was actually filed. services/governance/filing_export.py already
    established the right discipline for the older report_snapshots-based filings ("never recomputed or
    freshened"); this applies the identical discipline to the fund_sfdr_filings model.

    Returns (statement, is_frozen). is_frozen=False means there is no filed record for the current
    reference year — this is the legitimate pre-filing preview case, and the caller must disclose that
    (never present a live draft as if it were the filed record)."""
    live = sfdr_pai_statement(session, fund_id)
    if live.get("error"):
        return live, False
    ref_year = (live.get("summary") or {}).get("reference_year")
    if ref_year:
        row = session.execute(text("""
            SELECT statement FROM fund_sfdr_filings WHERE fund_id = :f AND reference_year = :y AND status = 'filed'
        """), {"f": fund_id, "y": ref_year}).scalar()
        if row:
            return row, True   # the exact frozen dict, byte-for-byte — never recomputed
    return live, False


def _entity_book(session, scope: dict, as_of=None) -> dict:
    """The entity's figures on one holdings date (default: each fund's latest) — every position of every fund of the
    manager, counted once, value-weighted. An empty book (positions 0) where none is on file for the date."""
    pai = fund_pai(session, None, **scope, as_of=as_of)
    if pai.get("positions", 0) == 0:
        return {"positions": 0, "total_value_eur": 0, "indicators": [], "sovereign_indicators": [],
                "real_estate_indicators": [], "additional_indicators": {}, "taxonomy": {}, "holdings_composition": {},
                "sovereign_countries": []}
    esg = fund_esg_pai(session, None, **scope, as_of=as_of)
    indicators, *_ = _mandatory_indicator_rows(pai, esg)
    comp = _composition_and_sovereign(session, None, **scope, as_of=as_of)
    return {
        "positions": pai["positions"], "total_value_eur": pai["total_value_eur"], "indicators": indicators,
        "sovereign_indicators": _sovereign_indicators(comp) if comp["sovereign_value_eur"] else [],
        "real_estate_indicators": _real_estate_indicators(comp),
        "additional_indicators": compute_voluntary_pai(session, None, comp, **scope, as_of=as_of),
        "taxonomy": _taxonomy_rollup(session, None, **scope, as_of=as_of),
        "holdings_composition": comp["by_asset_class"], "sovereign_countries": comp["sovereign_countries"],
        "emissions_coverage_pct": pai.get("emissions_coverage_pct"),
        "emissions_estimated_pct": pai.get("emissions_estimated_pct", 0.0),
        "pcaf_data_quality_score": pai.get("pcaf_data_quality_score"),
    }


def entity_pai_statement(session, org_id: str, period_end=None) -> dict:
    """Entity-level SFDR PAI statement (Delegated Regulation (EU) 2022/1288, Annex I) — one statement value-weighted
    across ALL of a manager's funds (every position counted once).

    period_end (a 31 December): the statement for that reference period — every impact the average of the impacts on
    31 March, 30 June, 30 September and 31 December (Article 6(3); ml.regulatory.sfdr_pai_period), with the sections
    the manager answers for that period, the previous period's figures (column 'Impact [year n-1]') and the historical
    comparison (Article 10) (services.governance.sfdr_pai_answers). Without it: a live view on each fund's latest
    holdings — not a statement for any period, and never filed."""
    from ml.regulatory.sfdr_pai_period import average_books, holdings_gaps, reference_dates
    org = session.execute(text("""
        SELECT o.org_id::text AS org_id, o.name, o.lei AS manager_lei, o.legal_name AS manager_legal_name,
               o.filing_contact_email, o.country AS manager_domicile
        FROM organizations o WHERE o.org_id = :o
    """), {"o": org_id}).mappings().first()
    if not org:
        return {"error": "organization not found"}

    fund_ids = session.execute(text("SELECT fund_id::text FROM funds WHERE org_id = :o"),
                               {"o": org_id}).scalars().all()
    if not fund_ids:
        return {"error": "manager has no funds"}
    scope = {"fund_ids": fund_ids, "org_id": org_id}

    dates = reference_dates(period_end) if period_end is not None else None      # PeriodError on a non-31-December end
    if dates:
        book = average_books({d: _entity_book(session, scope, as_of=d) for d in dates})
        gaps = holdings_gaps(session, fund_ids, dates)
    else:
        book, gaps = _entity_book(session, scope), []
    if book.get("positions", 0) == 0:
        return {"error": "manager has no positions to report on" + (f" in {dates[-1].year}" if dates else ""),
                "entity": {"manager": org["name"], "org_id": org["org_id"]}}
    indicators = book["indicators"]
    computed = sum(1 for i in indicators if i["method"] == "computed")
    partial = sum(1 for i in indicators if i["method"] == "partial")
    missing = sum(1 for i in indicators if i["method"] == "not_available")

    # Per-fund coverage table (top-level funds), so a thinly-covered fund inside the
    # entity total is visible rather than averaged away (on the period's last date).
    per_fund = []
    top = session.execute(text("""
        SELECT fund_id::text AS fund_id, name, sfdr_classification FROM funds
        WHERE org_id = :o AND parent_fund_id IS NULL ORDER BY name
    """), {"o": org_id}).mappings().all()
    for f in top:
        fp = fund_pai(session, f["fund_id"], as_of=dates[-1] if dates else None)
        per_fund.append({
            "fund_id": f["fund_id"], "fund_name": f["name"],
            "sfdr_classification": f["sfdr_classification"],
            "total_value_eur": fp.get("total_value_eur", 0),
            "positions": fp.get("positions", 0),
            "emissions_coverage_pct": fp.get("emissions_coverage_pct"),
        })

    manager_lei = org.get("manager_lei")
    filing_missing = []
    if not manager_lei:
        filing_missing.append("manager LEI")
    if not org.get("manager_legal_name"):
        filing_missing.append("manager legal name")
    if not org.get("filing_contact_email"):
        filing_missing.append("filing contact email")
    filing_missing += [f"holdings: {g}" for g in gaps]

    st = {
        "level": "entity",
        "entity": {
            "org_id": org["org_id"], "manager": org["name"], "manager_lei": manager_lei,
            "manager_legal_name": org.get("manager_legal_name"),
            "manager_domicile": org.get("manager_domicile"),
            "filing_contact_email": org.get("filing_contact_email"),
            "funds_count": len(top), "all_funds_scoped": len(fund_ids),
            "total_value_eur": book["total_value_eur"], "positions": book["positions"],
        },
        "reference_period": ({"start": f"{dates[-1].year}-01-01", "end": dates[-1].isoformat(),
                              "impact_dates": [d.isoformat() for d in dates],
                              "basis": "Delegated Regulation (EU) 2022/1288, Article 4(1) and Article 6(3)"}
                             if dates else None),
        "summary": {
            "pai_considered": True,
            "manager_lei_required": manager_lei is None,
            "reference_period": f"1 January – 31 December {dates[-1].year}" if dates
                                else "live view on the latest holdings — a statement is for a reference period",
            "declaration": (
                f"This is the entity-level principal adverse impacts statement of "
                f"{org.get('manager_legal_name') or org['name']} ({manager_lei or 'LEI required'}), "
                f"aggregated across {len(top)} fund(s). Principal adverse impacts of investment "
                "decisions on sustainability factors are considered."
            ),
        },
        "statement": "Entity-level Principal Adverse Impact (PAI) statement",
        "regulatory_basis": _pai_basis(),
        "indicators": indicators,
        "holdings_composition": book["holdings_composition"],
        "sovereign_indicators": book["sovereign_indicators"],
        "sovereign_countries": book["sovereign_countries"],
        "real_estate_indicators": book["real_estate_indicators"],
        "taxonomy": book["taxonomy"],
        "additional_indicators": book["additional_indicators"],
        "per_fund": per_fund,
        "coverage_summary": {
            "mandatory_indicators": len(indicators),
            "computed": computed, "partial": partial, "not_available": missing,
            "emissions_coverage_pct": book.get("emissions_coverage_pct"),
            "emissions_estimated_pct": book.get("emissions_estimated_pct"),
            "pcaf_data_quality_score": book.get("pcaf_data_quality_score"),
            "filing_readiness": (
                f"{computed} of {len(indicators)} mandatory indicators computed, {partial} partial, "
                f"{missing} awaiting issuer input — aggregated across {len(top)} fund(s), value-weighted"
                + (", each the average of the four quarter-end impacts." if dates else ".")
            ),
        },
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": _GOLDEN_SOURCE,
            "scope_note": "Entity-level: every position across all of the manager's funds, counted once, value-weighted"
                          + (f"; impacts averaged over {', '.join(d.isoformat() for d in dates)}." if dates
                             else "; each fund's latest holdings (live view)."),
        },
    }
    if dates:          # the sections the manager answers, the previous periods' figures (Articles 5-10)
        from services.governance import sfdr_pai_answers as A
        filing_missing += A.attach(session, org_id, dates[-1], st)
    st["filing_readiness"] = {
        "ready_to_file": bool(dates) and not filing_missing,
        "missing": filing_missing if dates else filing_missing + ["a reference period (a statement covers 1 January to "
                                                                   "31 December of one year)"],
        "note": "Ready to file." if dates and not filing_missing else "Not yet submittable — see what is missing.",
    }
    return st


# ── Downloadable filing document (.xlsx in the mandated table shape) ──
def _method_label(m: str) -> str:
    return {"computed": "Computed", "partial": "Partial (input needed)",
            "estimated": "Estimated", "not_available": "Not available — input required",
            "not_applicable": "Not applicable"}.get(m, m)


def _fmt_value(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, dict):
        return " · ".join(f"{k.replace('_', ' ')}: {v[k]:,}" if isinstance(v[k], (int, float)) else f"{k}: {v[k]}"
                          for k in v)
    if isinstance(v, (int, float)):
        return f"{v:,}"
    return str(v)


def _explanation(ind: dict, ref_year) -> str:
    """RTS 'Explanation' column: what the figure is, its coverage, and — honestly —
    where it's estimated or still needs input."""
    if ind["method"] == "computed":
        base = f"Computed ({ind['coverage_pct']}% coverage). Source: {ind['source']}."
    elif ind["method"] == "partial":
        base = f"Partial ({ind['coverage_pct']}% coverage). Source: {ind['source']}."
        if ind["input_required"]:
            base += f" To complete: {ind['input_required']}."
    elif ind["method"] == "estimated":
        base = f"Estimated. {ind['source']}."
    elif ind["method"] == "not_applicable":
        base = f"Not applicable — {ind['input_required']}." if ind["input_required"] else "Not applicable."
    else:
        base = f"Not available. Input required: {ind['input_required']}." if ind["input_required"] else "Not available."
    if ind.get("change_note"):
        base += f" {ind['change_note']}"
    return base


def sfdr_pai_statement_xlsx(statement: dict) -> io.BytesIO:
    """Render a filing-grade, multi-sheet workbook: Summary (RTS declaration),
    PAI statement (RTS Table 1 columns), and a Provenance & methodology appendix."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    title_font = Font(bold=True, size=14, color="1D1D1F")
    h2_font = Font(bold=True, size=12, color="1B54C4")
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1B54C4")
    label_font = Font(bold=True, color="48515F")
    wrap = Alignment(wrap_text=True, vertical="top")

    e = statement["entity"]
    summ = statement["summary"]
    prov = statement["provenance"]
    ref_year = summ.get("reference_year")
    wb = Workbook()

    # ── Sheet 1: Summary / declaration ──
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "Principal Adverse Impacts Statement — Summary"
    ws["A1"].font = title_font
    ws["A3"] = summ["declaration"]
    ws["A3"].alignment = wrap
    ws.merge_cells("A3:F5")
    rows = [
        ("Financial market participant (manager)", e["manager"]),
        ("Manager LEI", e.get("manager_lei") or "REQUIRED — supply the manager's LEI"),
        ("Fund", e["fund_name"]),
        ("SFDR product classification", e.get("sfdr_classification") or "—"),
        ("Reference period", summ["reference_period"]),
        ("Prior reference period", summ["prior_period"]),
        ("Principal adverse impacts considered", "Yes"),
        ("Portfolio value (EUR)", f"{e['total_value_eur']:,}"),
        ("Positions", e["positions"]),
        ("Regulatory basis", statement["regulatory_basis"]),
        ("Mandatory indicators computed", f"{statement['coverage_summary']['computed']} of {statement['coverage_summary']['mandatory_indicators']}"),
        ("Emissions coverage", f"{statement['coverage_summary']['emissions_coverage_pct']}% (of which {statement['coverage_summary']['emissions_estimated_pct']}% estimated)"),
        ("PCAF data-quality score", f"{statement['coverage_summary'].get('pcaf_data_quality_score', '—')} (1 best … 5 worst)"),
        ("Additional (voluntary) PAI", statement.get("additional_indicators", {}).get("status", "—")),
        ("Look-through", statement.get("look_through", {}).get("note") or statement.get("look_through", {}).get("status", "—")),
        ("Generated (UTC)", prov["generated_at"]),
    ]
    r = 7
    for k, v in rows:
        ws.cell(r, 1, k).font = label_font
        ws.cell(r, 2, v).alignment = wrap
        r += 1
    for i, w in enumerate([38, 62], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ── Sheet 2: PAI statement (RTS Table 1 columns) ──
    ws2 = wb.create_sheet("PAI statement")
    ref_lbl = summ["reference_period"]
    headers = ["#", "Adverse sustainability indicator", "Metric",
               f"Impact ({ref_lbl})", "Impact (prior period)", "Explanation",
               "Actions taken / planned & targets"]
    for c, h in enumerate(headers, 1):
        cell = ws2.cell(1, c, h)
        cell.font = head_font
        cell.fill = head_fill
        cell.alignment = wrap
    r = 2

    def _write_row(ind):
        nonlocal r
        ws2.cell(r, 1, ind["number"])
        ws2.cell(r, 2, ind["area"]).alignment = wrap
        ws2.cell(r, 3, f'{ind["metric"]} ({ind["unit"]})').alignment = wrap
        ws2.cell(r, 4, _fmt_value(ind["value"])).alignment = wrap
        ws2.cell(r, 5, statement["summary"]["prior_period"]).alignment = wrap
        ws2.cell(r, 6, _explanation(ind, ref_year)).alignment = wrap
        ws2.cell(r, 7, "[Manager to complete]").alignment = wrap
        r += 1

    def _section(label, items):
        nonlocal r
        if not items:
            return
        c = ws2.cell(r, 1, label)
        c.font = label_font
        r += 1
        for ind in items:
            _write_row(ind)

    _section("Investee companies (indicators 1–14)", statement["indicators"])
    _section("Sovereign & supranational (indicators 15–16)", statement.get("sovereign_indicators", []))
    _section("Real estate (indicators 17–18)", statement.get("real_estate_indicators", []))
    for i, w in enumerate([5, 26, 40, 24, 22, 60, 30], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    # ── Sheet 3: Provenance & methodology appendix ──
    ws3 = wb.create_sheet("Provenance & methodology")
    ws3["A1"] = "Provenance & methodology"
    ws3["A1"].font = title_font
    ws3["A3"] = "Data sources"
    ws3["A3"].font = h2_font
    for c, h in enumerate(["Item", "Source", "Vintage"], 1):
        cell = ws3.cell(4, c, h); cell.font = head_font; cell.fill = head_fill
    r = 5
    for ds in prov["data_sources"]:
        ws3.cell(r, 1, ds["item"]).alignment = wrap
        ws3.cell(r, 2, ds["source"]).alignment = wrap
        ws3.cell(r, 3, ds["vintage"]).alignment = wrap
        r += 1
    r += 1
    ws3.cell(r, 1, "Model versions").font = h2_font; r += 1
    for k, v in prov["model_versions"].items():
        ws3.cell(r, 1, k).font = label_font; ws3.cell(r, 2, v); r += 1
    r += 1
    ws3.cell(r, 1, "Disclosures").font = h2_font; r += 1
    d = prov["disclosures"]
    for k, v in [("Emissions coverage", f"{d['emissions_coverage_pct']}%"),
                 ("of which estimated", f"{d['emissions_estimated_pct']}%"),
                 ("Financed-emissions (EVIC) coverage", f"{d['financed_emissions_coverage_pct']}%")]:
        ws3.cell(r, 1, k).font = label_font; ws3.cell(r, 2, v); r += 1
    r += 1
    tax = statement["taxonomy"]
    ws3.cell(r, 1, "EU Taxonomy").font = h2_font; r += 1
    for k, v in [("Assessable share (has NACE)", f"{tax['assessable_pct']}%"),
                 ("Taxonomy-aligned", "Not asserted — " + tax["alignment_note"])]:
        ws3.cell(r, 1, k).font = label_font; ws3.cell(r, 2, v).alignment = wrap; r += 1
    r += 2
    ws3.cell(r, 1, "Methodology notes").font = h2_font; r += 1
    for note in [prov["scope_note"], prov["manager_actions_note"],
                 "Estimated figures use NACE sector-average intensity × revenue (EXIOBASE 3 sector intensities, "
                 "flagged as estimated); scope 3 is not estimated.",
                 "Financed emissions use the PCAF attribution factor (investment ÷ EVIC).",
                 "Unmatched securities and missing inputs are surfaced, never fabricated."]:
        ws3.cell(r, 1, note).alignment = wrap
        ws3.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        r += 1
    for i, w in enumerate([40, 46, 40], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    # Print setup so a PDF/print export is clean (customers often circulate a PDF).
    from openpyxl.worksheet.properties import PageSetupProperties
    for sheet, landscape in ((ws, False), (ws2, True), (ws3, False)):
        sheet.page_setup.orientation = "landscape" if landscape else "portrait"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
