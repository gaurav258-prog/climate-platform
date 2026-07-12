"""SFDR Article 8/9 PERIODIC disclosure (RTS Annex IV / V).

Distinct from the PAI statement: the periodic report is the fund-level disclosure
that accompanies the annual report, describing how far the fund's environmental/
social characteristics (Art 8) or sustainable objective (Art 9) were met over the
reference period, its asset allocation, its EU-Taxonomy alignment, its share of
sustainable investments, and its top holdings.

Same honesty discipline: sections we can compute from the golden source + the
manager's disclosures are filled; the sections that need the manager's own
per-holding classification (which investments count toward the E/S objective, and
which are "sustainable investments") are surfaced as inputs, never fabricated.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from services.asset_manager_engine import fund_descendant_ids
from services.fund_disclosure import fund_pai
# reuse the same honest Taxonomy roll-up the PAI statement uses
from ml.regulatory.sfdr_pai import _taxonomy_rollup


def _section(title, status, value=None, input_required=None, note=None):
    return {"section": title, "status": status, "value": value,
            "input_required": input_required, "note": note}


def periodic_report(session, fund_id: str) -> dict:
    fund = session.execute(text("""
        SELECT f.fund_id::text AS fund_id, f.name, f.sfdr_classification, f.base_currency,
               o.name AS org_name, o.lei AS manager_lei
        FROM funds f JOIN organizations o ON o.org_id = f.org_id
        WHERE f.fund_id = :f
    """), {"f": fund_id}).mappings().first()
    if not fund:
        return {"error": "fund not found"}
    if fund["sfdr_classification"] not in ("article_8", "article_9"):
        return {"error": "periodic report applies to Article 8 or 9 products only",
                "sfdr_classification": fund["sfdr_classification"]}

    pai = fund_pai(session, fund_id)
    if pai.get("positions", 0) == 0:
        return {"error": "fund has no positions", "fund": dict(fund)}
    tax = _taxonomy_rollup(session, fund_id)

    # Top investments (value-weighted, latest snapshot across the fund + sub-funds).
    fund_ids = fund_descendant_ids(session, fund_id)
    top = session.execute(text("""
        SELECT i.name AS issuer, i.country, i.nace_code, s.asset_class,
               CAST(p.market_value_eur AS FLOAT) AS mv
        FROM fund_positions p JOIN securities s ON s.security_id = p.security_id
        JOIN issuers i ON i.issuer_id = s.issuer_id
        WHERE p.fund_id = ANY(:fids)
          AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
        ORDER BY p.market_value_eur DESC LIMIT 10
    """), {"fids": fund_ids}).mappings().all()
    total = pai["total_value_eur"] or 1
    top_investments = [{"issuer": r["issuer"], "country": r["country"], "sector_nace": r["nace_code"],
                        "asset_class": r["asset_class"], "value_eur": round(r["mv"]),
                        "weight_pct": round(100 * r["mv"] / total, 2)} for r in top]

    art = fund["sfdr_classification"]
    sections = [
        _section(
            "Did this financial product have sustainable investment objective / E&S characteristics?",
            "computed", value="Sustainable investment objective (Article 9)" if art == "article_9"
            else "Promotes environmental/social characteristics (Article 8)"),
        _section(
            "To what extent were the E/S characteristics met?",
            "partial",
            value={"waci_tco2e_per_meur": pai["pai"]["pai_3_waci_tco2e_per_meur"],
                   "fossil_fuel_exposure_pct": pai["pai"]["pai_4_fossil_fuel_exposure_pct"],
                   "emissions_coverage_pct": pai["emissions_coverage_pct"]},
            input_required="the manager's qualitative attainment assessment vs the stated characteristics",
            note="Sustainability indicators are computed from the golden source; the narrative "
                 "attainment statement is the manager's."),
        _section(
            "EU Taxonomy alignment of investments",
            "computed" if tax.get("taxonomy_aligned_pct") is not None else "not_available",
            value={"taxonomy_aligned_pct": tax.get("taxonomy_aligned_pct"),
                   "taxonomy_eligible_pct": tax.get("taxonomy_eligible_pct"),
                   "reported_coverage_pct": tax.get("alignment_coverage_pct")},
            input_required=tax.get("input_required")),
        _section(
            "What was the asset allocation? (#1 aligned with E/S · #2 other)",
            "partial",
            value={"taxonomy_aligned_pct": tax.get("taxonomy_aligned_pct")},
            input_required="the manager's per-holding classification of which investments count "
                           "toward the E/S characteristics (#1) vs other (#2)"),
        _section(
            "What was the share of sustainable investments?",
            "not_available",
            input_required="per-holding 'sustainable investment' flag (the manager's SFDR Art 2(17) assessment)"),
        _section(
            "Principal adverse impacts considered?",
            "computed", value="Yes — see the fund's SFDR PAI statement",
            note="The mandatory PAI indicators are produced by the PAI statement endpoint."),
    ]

    computed = sum(1 for s in sections if s["status"] == "computed")
    return {
        "entity": {"fund_id": fund["fund_id"], "fund_name": fund["name"], "manager": fund["org_name"],
                   "manager_lei": fund["manager_lei"], "sfdr_classification": art,
                   "total_value_eur": pai["total_value_eur"], "positions": pai["positions"]},
        "report": "SFDR periodic disclosure",
        "regulatory_basis": f"SFDR RTS Annex {'V (Article 9)' if art == 'article_9' else 'IV (Article 8)'}",
        "sections": sections,
        "top_investments": top_investments,
        "coverage_summary": {
            "sections": len(sections), "computed": computed,
            "note": "Quantitative sections are computed from the golden source; sections needing the "
                    "manager's own per-holding E/S and sustainable-investment classification are flagged "
                    "as required inputs, not fabricated.",
        },
        "provenance": {"generated_at": datetime.now(timezone.utc).isoformat()},
    }
