"""EBA Pillar 3 ESG risk disclosure templates — built to the ACTUAL regulatory structure (ITS (EU) 2022/2453,
Annex XXXIX templates / Annex XL instructions), not a readable summary.

This module holds the pure, testable computation of the quantitative grids from a bank's per-asset book. It
is deliberately honest about the axes we can vs. cannot populate from our golden source:

  Template 5 (physical risk) — rows = NACE section × the physical-risk columns. We COMPUTE, from the book:
    • (b) gross carrying amount            — outstanding loan balance per exposure
    • of which physical-risk-sensitive      — exposures in the top-two severity bands (H/VH) on any climate peril
    • (h) chronic / (i) acute / (j) both    — from each exposure's per-hazard chronic-vs-acute High+ hits
  We CANNOT compute from our feeds (→ customer IFRS-9 / loan-book data, left blank, never fabricated):
    • (c–g) maturity buckets                — no maturity date in the loan schema (only origination date)
    • (k–o) Stage 2 / non-performing / accumulated impairment — IFRS-9 credit-quality, not a climate feed

Chronic vs. acute allocation: the ITS leaves the split to the institution's methodology (Annex XL). We use the
TCFD convention — acute = event-driven perils, chronic = gradual shifts — documented below and overridable.
"""
from __future__ import annotations

# TCFD/EBA physical-climate split. ACUTE = sudden event-driven; CHRONIC = long-term/gradual shifts. Non-climate
# perils (seismic, volcanic) and out-of-scope pollution are excluded from Template 5 (climate physical risk only).
ACUTE_HAZARDS = frozenset({"flood", "storm", "wildfire", "heat_acute", "frost"})
CHRONIC_HAZARDS = frozenset({"drought", "heat_chronic", "soil_water", "coastal_flood", "water_stress"})
_HIGH_BUCKETS = frozenset({"H", "VH"})

# NACE section (letter) → official title (Reg (EC) 1893/2006, Annex I section headers). Template 5 rows are by
# sector; we bucket each exposure's NACE code to its section letter and label it with the official section name.
NACE_SECTIONS: dict[str, str] = {
    "A": "Agriculture, forestry and fishing", "B": "Mining and quarrying", "C": "Manufacturing",
    "D": "Electricity, gas, steam and air conditioning supply", "E": "Water supply; sewerage, waste management",
    "F": "Construction", "G": "Wholesale and retail trade; repair of motor vehicles",
    "H": "Transportation and storage", "I": "Accommodation and food service activities",
    "J": "Information and communication", "K": "Financial and insurance activities",
    "L": "Real estate activities", "M": "Professional, scientific and technical activities",
    "N": "Administrative and support service activities", "O": "Public administration and defence",
    "P": "Education", "Q": "Human health and social work activities",
    "R": "Arts, entertainment and recreation", "S": "Other service activities",
    "T": "Activities of households as employers", "U": "Activities of extraterritorial organisations",
}


def _section(nace_code) -> str:
    """Map a NACE code to its section letter. NACE codes are like '01.11' (division) or 'A' — we take the
    leading letter if present, else map the leading 2-digit division to its section per Reg 1893/2006."""
    if not nace_code:
        return "?"
    s = str(nace_code).strip().upper()
    if s[:1].isalpha() and s[:1] in NACE_SECTIONS:
        return s[:1]
    # numeric division → section (Reg 1893/2006 division→section ranges)
    div = ""
    for ch in s:
        if ch.isdigit():
            div += ch
        elif div:
            break
    if not div:
        return "?"
    d = int(div[:2]) if len(div) >= 2 else int(div)
    ranges = [(1, 3, "A"), (5, 9, "B"), (10, 33, "C"), (35, 35, "D"), (36, 39, "E"), (41, 43, "F"),
              (45, 47, "G"), (49, 53, "H"), (55, 56, "I"), (58, 63, "J"), (64, 66, "K"), (68, 68, "L"),
              (69, 75, "M"), (77, 82, "N"), (84, 84, "O"), (85, 85, "P"), (86, 88, "Q"), (90, 93, "R"),
              (94, 96, "S"), (97, 98, "T"), (99, 99, "U")]
    for lo, hi, sec in ranges:
        if lo <= d <= hi:
            return sec
    return "?"


def _asset_hits(asset: dict) -> tuple[bool, bool]:
    """(chronic_hit, acute_hit) — is this exposure sensitive to a High+ chronic / acute climate peril?
    Reads the asset's per-hazard list; an exposure counts for a category if ANY of its hazards in that
    category sits in the top-two severity bands (H/VH)."""
    chronic = acute = False
    for h in asset.get("hazards") or []:
        if h.get("bucket") not in _HIGH_BUCKETS:
            continue
        hz = h.get("hazard")
        if hz in CHRONIC_HAZARDS:
            chronic = True
        elif hz in ACUTE_HAZARDS:
            acute = True
    return chronic, acute


def template1_grid(assets: list[dict]) -> dict:
    """EBA Pillar 3 Template 1 — banking-book transition-risk exposure by NACE sector (ITS 2022/2453,
    Annex XXXIX / Annex XL). Columns a–p verified verbatim from Annex XL. We COMPUTE the columns our golden
    source supports: (a) gross carrying amount and (i) GHG financed emissions Scope 1+2+3 with (j) of-which
    Scope 3 — using the SAME per-asset ghg figures the platform already sums for financed emissions (no new
    attribution). The credit-quality (d–h), Paris-benchmark-exclusion (b), env-sustainable/aligned (c),
    %-company-reported (k) and maturity (l–p) columns are customer/IFRS-9 data, declared and left blank."""
    by_sector: dict[str, dict] = {}
    for a in assets:
        gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        if not gross:
            continue
        sec = _section(a.get("nace_code"))
        s1, s2, s3 = (a.get("ghg1") or 0), (a.get("ghg2") or 0), (a.get("ghg3") or 0)
        row = by_sector.setdefault(sec, {"section": sec, "label": NACE_SECTIONS.get(sec, "Unclassified"),
                                         "gross": 0.0, "fin_emissions": 0.0, "scope3": 0.0})
        row["gross"] += gross
        row["fin_emissions"] += s1 + s2 + s3
        row["scope3"] += s3
    rows = sorted(by_sector.values(), key=lambda r: (r["section"] == "?", r["section"]))
    total = {"section": "TOTAL", "label": "Total", "gross": sum(r["gross"] for r in rows),
             "fin_emissions": sum(r["fin_emissions"] for r in rows), "scope3": sum(r["scope3"] for r in rows)}
    _round = lambda r: {k: (round(v) if isinstance(v, float) else v) for k, v in r.items()}
    return {
        "rows": [_round(r) for r in rows], "total": _round(total),
        "customer_columns": ["of which environmentally sustainable / Taxonomy-aligned (CCM)",
                             "of which excluded from EU Paris-aligned Benchmarks", "Stage 2 (IFRS 9)",
                             "non-performing exposures", "accumulated impairment",
                             "% of emissions from company-specific reporting",
                             "maturity buckets (≤5y / 5–10y / 10–20y / >20y / avg-weighted)"],
        "basis": "Gross carrying amount = outstanding loan balance. Financed emissions (Scope 1+2+3) and of-which "
                 "Scope 3 sum the per-counterparty GHG figures on the book (the platform's financed-emissions "
                 "basis). Credit-quality, alignment, Paris-benchmark and maturity columns are customer-supplied.",
    }


def template5_grid(assets: list[dict]) -> dict:
    """EBA Pillar 3 Template 5 — banking-book physical-risk exposure by NACE sector. Returns the computable
    columns (gross carrying amount, of-which physical-risk-sensitive, chronic, acute, both) per sector + total,
    and names the customer-supplied columns (maturity buckets, IFRS-9 credit quality) left blank by design."""
    by_sector: dict[str, dict] = {}
    for a in assets:
        gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        if not gross:
            continue
        sec = _section(a.get("nace_code"))
        chronic, acute = _asset_hits(a)
        sensitive = chronic or acute
        row = by_sector.setdefault(sec, {"section": sec, "label": NACE_SECTIONS.get(sec, "Unclassified"),
                                         "gross": 0.0, "sensitive": 0.0, "chronic": 0.0, "acute": 0.0, "both": 0.0})
        row["gross"] += gross
        if sensitive:
            row["sensitive"] += gross
        if chronic:
            row["chronic"] += gross
        if acute:
            row["acute"] += gross
        if chronic and acute:
            row["both"] += gross

    rows = sorted(by_sector.values(), key=lambda r: (r["section"] == "?", r["section"]))
    total = {"section": "TOTAL", "label": "Total", "gross": sum(r["gross"] for r in rows),
             "sensitive": sum(r["sensitive"] for r in rows), "chronic": sum(r["chronic"] for r in rows),
             "acute": sum(r["acute"] for r in rows), "both": sum(r["both"] for r in rows)}
    return {
        "rows": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()} for r in rows],
        "total": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in total.items()},
        # the official columns we cannot source from our feeds — declared, not silently dropped
        "customer_columns": ["maturity buckets (≤5y / 5–10y / 10–20y / >20y / avg-weighted)",
                             "Stage 2 (IFRS 9)", "non-performing exposures", "accumulated impairment"],
        "basis": "Gross carrying amount = outstanding loan balance. 'Of which physical-risk-sensitive' = "
                 "exposures in the top-two severity bands (H/VH). Chronic/acute per the institution's "
                 "methodology (TCFD split). Maturity + IFRS-9 credit-quality columns are customer-supplied.",
    }
