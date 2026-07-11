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

What is computed today (from services/fund_disclosure.fund_pai):
    * PAI 3  — GHG intensity of investees (WACI)          — computed
    * PAI 4  — fossil-fuel-sector exposure                — computed
    * PAI 1  — investee GHG emissions (un-attributed)     — partial (needs EVIC
                                                            for PCAF attribution)
Everything else in Table 1 needs issuer data we do not yet hold (energy mix,
water, waste, social/governance) and is surfaced as an input gap.

Scope: investee-company indicators (equity / corporate-bond funds), which is the
beachhead. Sovereign (Table 1, indicators 15-16) and real-estate (17-18) tables
are out of scope for this first version and flagged as such.
"""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from services.fund_disclosure import fund_pai

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

_GOLDEN_SOURCE = "Tellumen golden source (issuer emissions + revenue, provenance-stamped)"


def _row(num, area, metric, unit, *, value=None, coverage=None, source=None,
         method="not_available", input_required=None):
    """One indicator line. method ∈ computed / partial / estimated / not_available."""
    return {
        "number": num, "area": area, "metric": metric, "unit": unit,
        "value": value, "coverage_pct": coverage, "source": source,
        "method": method, "input_required": input_required,
    }


def _taxonomy_rollup(session, fund_id: str) -> dict:
    """EU Taxonomy lines for the fund, honestly scoped.

    Eligibility can only be judged where we hold the issuer's NACE code; alignment
    is never asserted (DNSH across the six objectives + minimum safeguards are not
    verified) — matching the classifier's discipline. We report the share of value
    we can even assess, so the gap is explicit.
    """
    rows = session.execute(text("""
        SELECT p.market_value_eur AS mv, i.nace_code
        FROM   fund_positions p
        JOIN   securities s ON s.security_id = p.security_id
        JOIN   issuers   i ON i.issuer_id = s.issuer_id
        WHERE  p.fund_id = :f
    """), {"f": fund_id}).mappings().all()
    total = sum(float(r["mv"]) for r in rows) or 0.0
    with_nace = sum(float(r["mv"]) for r in rows if r["nace_code"])
    return {
        "assessable_pct": round(100 * with_nace / total, 1) if total else 0.0,
        "taxonomy_eligible_pct": None if with_nace == 0 else "requires per-issuer NACE mapping",
        "taxonomy_aligned_pct": None,
        "alignment_note": "Alignment not asserted: DNSH across the six environmental "
                          "objectives and minimum-safeguards verification are not performed. "
                          "Reported as eligible-at-most, never aligned.",
        "input_required": "issuer NACE code (absent from GLEIF; supply per issuer or via a fundamentals upload)",
    }


def sfdr_pai_statement(session, fund_id: str) -> dict:
    """Assemble the fund's full SFDR PAI statement (Annex I Table 1) + Taxonomy.

    Returns a structured, filing-shaped dict: entity metadata, the 14 mandatory
    indicators (filled or gap-flagged), Taxonomy lines, a coverage summary, and
    provenance. Raises nothing for missing data — it is disclosed, not hidden.
    """
    fund = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.sfdr_classification, f.base_currency,
               o.name AS org_name
        FROM funds f JOIN organizations o ON o.org_id = f.org_id
        WHERE f.fund_id = :f
    """), {"f": fund_id}).mappings().first()
    if not fund:
        return {"error": "fund not found"}

    pai = fund_pai(session, fund_id)
    if pai.get("positions", 0) == 0:
        return {"error": "fund has no positions to report on", "fund": dict(fund)}

    p = pai["pai"]
    emis_cov = pai.get("emissions_coverage_pct")
    inv = p["pai_1_investee_emissions_tco2e"]

    # Fill the mandatory table: computed where we honestly can, gap-flagged otherwise.
    filled: dict[int, dict] = {}

    # PAI 1 — investee GHG emissions (un-attributed; financed-emissions attribution needs EVIC)
    filled[1] = _row(1, "Climate & environment",
                     "GHG emissions (Scope 1, 2 and 3, and total)", "tCO₂e",
                     value={"scope_1": inv["scope_1"], "scope_2": inv["scope_2"],
                            "scope_3": inv["scope_3"],
                            "total": inv["scope_1"] + inv["scope_2"] + inv["scope_3"]},
                     coverage=emis_cov, source=_GOLDEN_SOURCE, method="partial",
                     input_required="issuer EVIC (enterprise value incl. cash) to attribute "
                                    "financed emissions per PCAF")
    # PAI 2 — carbon footprint (financed emissions / €M invested) — needs EVIC
    filled[2] = _row(2, "Climate & environment",
                     "Carbon footprint (financed emissions per €M invested)", "tCO₂e/€M",
                     method="not_available",
                     input_required="issuer EVIC (to compute the PCAF attribution factor)")
    # PAI 3 — WACI (computed)
    filled[3] = _row(3, "Climate & environment",
                     "GHG intensity of investee companies (WACI)", "tCO₂e/€M revenue",
                     value=p["pai_3_waci_tco2e_per_meur"], coverage=emis_cov,
                     source=_GOLDEN_SOURCE,
                     method="computed" if p["pai_3_waci_tco2e_per_meur"] is not None else "not_available",
                     input_required=None if p["pai_3_waci_tco2e_per_meur"] is not None
                     else "issuer Scope 1/2 emissions + revenue")
    # PAI 4 — fossil-fuel-sector exposure (computed from NACE)
    filled[4] = _row(4, "Climate & environment",
                     "Exposure to companies active in the fossil fuel sector", "% of value",
                     value=p["pai_4_fossil_fuel_exposure_pct"], coverage=100.0,
                     source="issuer NACE division (golden source)", method="computed")

    # Inputs each remaining mandatory indicator needs (all currently not available).
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

    indicators = []
    for num, area, metric, unit in MANDATORY_PAI_INDICATORS:
        if num in filled:
            indicators.append(filled[num])
        else:
            indicators.append(_row(num, area, metric, unit,
                                   input_required=remaining_inputs.get(num)))

    computed = sum(1 for i in indicators if i["method"] == "computed")
    partial = sum(1 for i in indicators if i["method"] == "partial")
    missing = sum(1 for i in indicators if i["method"] == "not_available")

    return {
        "entity": {
            "fund_id": fund["fund_id"], "fund_name": fund["name"],
            "manager": fund["org_name"], "base_currency": fund["base_currency"],
            "sfdr_classification": fund["sfdr_classification"],
            "total_value_eur": pai["total_value_eur"], "positions": pai["positions"],
        },
        "statement": "Principal Adverse Impact (PAI) statement",
        "regulatory_basis": "SFDR RTS — Commission Delegated Regulation (EU) 2022/1288, Annex I, Table 1",
        "indicators": indicators,
        "taxonomy": _taxonomy_rollup(session, fund_id),
        "coverage_summary": {
            "mandatory_indicators": len(indicators),
            "computed": computed, "partial": partial, "not_available": missing,
            "emissions_coverage_pct": emis_cov,
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
            "scope_note": "Investee-company indicators only (equity / corporate bonds). "
                          "Sovereign and real-estate PAI tables are out of scope for this statement.",
        },
    }


# ── Downloadable filing document (.xlsx in the mandated table shape) ──
def _method_label(m: str) -> str:
    return {"computed": "Computed", "partial": "Partial (input needed)",
            "estimated": "Estimated", "not_available": "Not available — input required"}.get(m, m)


def _fmt_value(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, dict):
        return " · ".join(f"{k.replace('_', ' ')}: {v[k]:,}" if isinstance(v[k], (int, float)) else f"{k}: {v[k]}"
                          for k in v)
    if isinstance(v, (int, float)):
        return f"{v:,}"
    return str(v)


def sfdr_pai_statement_xlsx(statement: dict) -> io.BytesIO:
    """Render the assembled statement as a formatted, filer-usable .xlsx document."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    title_font = Font(bold=True, size=14, color="1D1D1F")
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1B54C4")
    label_font = Font(bold=True, color="48515F")
    wrap = Alignment(wrap_text=True, vertical="top")

    wb = Workbook()
    ws = wb.active
    ws.title = "SFDR PAI Statement"
    e = statement["entity"]

    ws["A1"] = "Principal Adverse Impact (PAI) Statement"
    ws["A1"].font = title_font
    meta = [
        ("Fund", e["fund_name"]), ("Manager", e["manager"]),
        ("SFDR classification", e.get("sfdr_classification") or "—"),
        ("Portfolio value (EUR)", f"{e['total_value_eur']:,}"),
        ("Positions", e["positions"]),
        ("Regulatory basis", statement["regulatory_basis"]),
        ("Generated (UTC)", statement["provenance"]["generated_at"]),
    ]
    r = 3
    for k, v in meta:
        ws.cell(r, 1, k).font = label_font
        ws.cell(r, 2, v)
        r += 1

    r += 1
    headers = ["#", "Area", "Adverse impact indicator", "Value", "Unit", "Coverage", "Data source / status"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(r, c, h)
        cell.font = head_font
        cell.fill = head_fill
    r += 1
    for ind in statement["indicators"]:
        status = ind["source"] if ind["method"] in ("computed", "partial") else _method_label(ind["method"])
        if ind["input_required"]:
            status = f"{status} — needs: {ind['input_required']}" if ind["method"] == "partial" \
                else f"Input required: {ind['input_required']}"
        ws.cell(r, 1, ind["number"])
        ws.cell(r, 2, ind["area"])
        ws.cell(r, 3, ind["metric"]).alignment = wrap
        ws.cell(r, 4, _fmt_value(ind["value"]))
        ws.cell(r, 5, ind["unit"])
        ws.cell(r, 6, "—" if ind["coverage_pct"] is None else f"{ind['coverage_pct']}%")
        ws.cell(r, 7, status).alignment = wrap
        r += 1

    r += 1
    ws.cell(r, 1, "EU Taxonomy").font = label_font
    r += 1
    tax = statement["taxonomy"]
    for k, v in [("Assessable share (has NACE)", f"{tax['assessable_pct']}%"),
                 ("Taxonomy-eligible", _fmt_value(tax["taxonomy_eligible_pct"])),
                 ("Taxonomy-aligned", "Not asserted"),
                 ("Note", tax["alignment_note"])]:
        ws.cell(r, 1, k).font = label_font
        ws.cell(r, 3, v).alignment = wrap
        r += 1

    r += 1
    ws.cell(r, 1, "Coverage").font = label_font
    ws.cell(r, 3, statement["coverage_summary"]["filing_readiness"]).alignment = wrap

    widths = [5, 20, 46, 26, 16, 10, 52]
    from openpyxl.utils import get_column_letter
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
