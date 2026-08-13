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


# GAR counterparty classes (Template 7 row axis, mapped from NACE). General government is shown but EXCLUDED
# from the GAR denominator per Art. 7(1) of Del. Reg. (EU) 2021/2178 (central govts, central banks and
# supranationals are out of both numerator and denominator).
def _gar_counterparty(sec: str) -> str:
    if sec == "K":
        return "Financial corporations"
    if sec == "O":
        return "General governments"            # excluded from covered assets
    if sec == "?":
        return "Households & other"              # retail / no NACE on the exposure
    return "Non-financial corporations"


def gar_grid(assets: list[dict]) -> dict:
    """EBA Pillar 3 Green Asset Ratio (Templates 6–8, ITS (EU) 2022/2453 / Del. Reg. 2021/2178). Computes what
    the book supports: gross carrying amount, Taxonomy-ELIGIBLE and Taxonomy-ALIGNED amounts by counterparty
    class, the GAR covered-assets denominator (total EXCLUDING general governments, Art. 7), and the GAR ratio
    on stock. Eligibility/alignment read the per-asset `taxonomy_status` our classifier already sets (aligned ⊆
    eligible); full alignment needs the technical screening criteria + DNSH, so where the book is only classified
    to eligibility the aligned figure is a floor. The CCM/CCA per-objective split (Template 6 columns) needs a
    per-activity objective mapping we don't hold — declared, not fabricated."""
    by_cls: dict[str, dict] = {}
    for a in assets:
        gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        if not gross:
            continue
        cls = _gar_counterparty(_section(a.get("nace_code")))
        st = (a.get("taxonomy_status") or "").strip().lower()
        row = by_cls.setdefault(cls, {"counterparty": cls, "gross": 0.0, "eligible": 0.0, "aligned": 0.0})
        row["gross"] += gross
        if st == "aligned":
            row["aligned"] += gross
            row["eligible"] += gross          # aligned is a subset of eligible
        elif st == "eligible":
            row["eligible"] += gross
    order = ["Financial corporations", "Non-financial corporations", "Households & other", "General governments"]
    rows = sorted(by_cls.values(), key=lambda r: order.index(r["counterparty"]) if r["counterparty"] in order else 99)
    total = sum(r["gross"] for r in rows)
    govt = sum(r["gross"] for r in rows if r["counterparty"] == "General governments")
    covered = total - govt                     # GAR denominator excludes general governments (Art. 7)
    eligible = sum(r["eligible"] for r in rows if r["counterparty"] != "General governments")
    aligned = sum(r["aligned"] for r in rows if r["counterparty"] != "General governments")
    _r = lambda v: round(v) if isinstance(v, float) else v
    return {
        "rows": [{k: _r(v) for k, v in r.items()} for r in rows],
        "total_assets": _r(total), "covered_assets": _r(covered), "general_government": _r(govt),
        "eligible": _r(eligible), "aligned": _r(aligned),
        "pct_eligible": round(eligible / covered * 100, 1) if covered else None,
        "gar_stock_pct": round(aligned / covered * 100, 1) if covered else None,
        "customer_columns": ["CCM / CCA per-objective split (needs per-activity objective mapping)",
                             "GAR on flow (new lending in the period)", "specialised-lending / of-which enabling / transitional"],
        "basis": "Green Asset Ratio on stock = Taxonomy-aligned / covered assets. Covered assets EXCLUDE general "
                 "governments (central govts, central banks, supranationals) per Art. 7(1). Eligible/aligned read "
                 "the book's per-asset taxonomy_status (aligned ⊆ eligible); full alignment additionally needs the "
                 "technical screening criteria + DNSH, so an eligibility-only classification makes aligned a floor.",
    }


# EBA "sectors that highly contribute to climate change" (high-climate-impact sectors) — NACE sections A–H, L.
HIGH_CLIMATE_NACE = frozenset({"A", "B", "C", "D", "E", "F", "G", "H", "L"})


def concentration_split(assets: list[dict]) -> dict:
    """Decision/concentration measures over the banking book, from the SAME per-asset fields the Pillar 3
    templates use: acute- vs chronic-peril exposure (Template 5 split), and concentration in the EBA high-
    climate-impact NACE sectors (the axis of Templates 1 & 5), with the single most-concentrated sector.
    Acute and chronic overlap where an exposure faces both — they are lenses on the at-risk book, not a
    partition. Nothing new-sourced."""
    acute_val = chronic_val = hci_val = 0.0
    sector_val: dict[str, float] = {}
    for a in assets:
        v = a.get("value_eur") or a.get("outstanding_loan_balance_eur") or 0
        if not v:
            continue
        chronic, acute = _asset_hits(a)
        if acute:
            acute_val += v
        if chronic:
            chronic_val += v
        sec = _section(a.get("nace_code"))
        sector_val[sec] = sector_val.get(sec, 0.0) + v
        if sec in HIGH_CLIMATE_NACE:
            hci_val += v
    top_sec, top_val = max(sector_val.items(), key=lambda kv: kv[1], default=("?", 0.0))
    return {"acute_val": acute_val, "chronic_val": chronic_val, "high_climate_val": hci_val,
            "top_sector": top_sec, "top_sector_val": top_val, "by_sector": sector_val}


def _mat_bucket(m: float) -> str:
    return "le5" if m <= 5 else "m5_10" if m <= 10 else "m10_20" if m <= 20 else "gt20"


def template5_grid(assets: list[dict]) -> dict:
    """EBA Pillar 3 Template 5 — banking-book physical-risk exposure by NACE sector. Returns the computable
    columns (gross carrying amount, of-which physical-risk-sensitive, chronic, acute, both) per sector + total.
    The maturity buckets and IFRS-9 credit-quality columns are filled from the per-loan attributes the customer
    provides (residual_maturity_years, ifrs9_stage) where present; sectors/columns without that data stay blank."""
    _M = ("le5", "m5_10", "m10_20", "gt20")
    by_sector: dict[str, dict] = {}
    mat_n, ifrs9_n = 0, 0
    for a in assets:
        gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        if not gross:
            continue
        sec = _section(a.get("nace_code"))
        chronic, acute = _asset_hits(a)
        sensitive = chronic or acute
        row = by_sector.setdefault(sec, {"section": sec, "label": NACE_SECTIONS.get(sec, "Unclassified"),
                                         "gross": 0.0, "sensitive": 0.0, "chronic": 0.0, "acute": 0.0, "both": 0.0,
                                         "le5": 0.0, "m5_10": 0.0, "m10_20": 0.0, "gt20": 0.0,
                                         "_mat_x_gross": 0.0, "_mat_gross": 0.0,
                                         "stage2": 0.0, "npe": 0.0, "_ifrs9_gross": 0.0})
        row["gross"] += gross
        if sensitive:
            row["sensitive"] += gross
        if chronic:
            row["chronic"] += gross
        if acute:
            row["acute"] += gross
        if chronic and acute:
            row["both"] += gross
        # maturity buckets + gross-weighted average, from the provided residual maturity
        m = a.get("residual_maturity_years")
        if m is not None:
            try:
                mv = float(m)
                mat_n += 1
                row[_mat_bucket(mv)] += gross
                row["_mat_x_gross"] += gross * mv
                row["_mat_gross"] += gross
            except (TypeError, ValueError):
                pass
        # IFRS-9 staging: Stage 2 (under-performing) and Stage 3 (non-performing) from the provided stage
        st = str(a.get("ifrs9_stage") or "").strip().lower().replace("stage", "").strip()
        if st:
            ifrs9_n += 1
            row["_ifrs9_gross"] += gross
            if st in ("2", "2 "):
                row["stage2"] += gross
            elif st in ("3",):
                row["npe"] += gross

    def _avg(r):
        return round(r["_mat_x_gross"] / r["_mat_gross"], 1) if r["_mat_gross"] else None

    rows = sorted(by_sector.values(), key=lambda r: (r["section"] == "?", r["section"]))
    tot = {"section": "TOTAL", "label": "Total"}
    for k in ("gross", "sensitive", "chronic", "acute", "both", "le5", "m5_10", "m10_20", "gt20",
              "stage2", "npe", "_mat_x_gross", "_mat_gross", "_ifrs9_gross"):
        tot[k] = sum(r[k] for r in rows)

    def _emit(r):
        out = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if not k.startswith("_")}
        out["avg_maturity"] = _avg(r)
        out["has_maturity"] = r["_mat_gross"] > 0    # this sector has maturity data → show its bucket cells
        out["has_ifrs9"] = r["_ifrs9_gross"] > 0     # this sector has IFRS-9 staging → show its stage cells
        return out

    return {
        "rows": [_emit(r) for r in rows],
        "total": _emit(tot),
        "maturity_covered": mat_n > 0,   # show the maturity columns only when the loan tape carries maturity
        "ifrs9_covered": ifrs9_n > 0,     # show the IFRS-9 columns only when staging is provided
        # any official column still unsourced is declared, not silently dropped
        "customer_columns": ([] if mat_n and ifrs9_n else
                             (["Stage 2 / non-performing (IFRS 9)"] if not ifrs9_n else []) +
                             (["maturity buckets"] if not mat_n else [])) + ["accumulated impairment"],
        "basis": "Gross carrying amount = outstanding loan balance. 'Of which physical-risk-sensitive' = "
                 "exposures in the top-two severity bands (H/VH). Chronic/acute per the institution's "
                 "methodology (TCFD split). Maturity buckets + IFRS-9 staging are filled from the loan-tape "
                 "attributes you provide (residual maturity, IFRS-9 stage); columns without that data stay blank.",
    }
