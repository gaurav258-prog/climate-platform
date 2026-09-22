"""EBA Pillar 3 ESG risk disclosure templates — built to the ACTUAL regulatory structure (ITS (EU) 2022/2453,
Annex XXXIX templates / Annex XL instructions), not a readable summary.

This module holds the pure, testable computation of the quantitative grids from a bank's per-asset book. It
is deliberately honest about the axes we can vs. cannot populate from our golden source:

  Template 1 (transition risk) and Template 5 (physical risk) — rows = NACE section × the risk columns. We
  COMPUTE, from the book:
    • (b) gross carrying amount             — outstanding loan balance per exposure
    • Template 5's of-which physical-risk-sensitive / chronic / acute / both — from each exposure's per-hazard
      chronic-vs-acute High+ hits
    • maturity buckets + gross-weighted average maturity, and IFRS-9 Stage 2 / non-performing — from the
      per-loan `residual_maturity_years` / `ifrs9_stage` attributes the customer provides (Data → provide by
      Excel); a sector/loan without that attribute stays blank, never fabricated, and a book-wide
      `maturity_covered` / `ifrs9_covered` flag says whether the columns are shown at all.
  We CANNOT compute from our feeds (→ customer/company data, left blank, never fabricated):
    • Template 1: environmentally-sustainable/Taxonomy-aligned (CCM), Paris-benchmark exclusion, accumulated
      impairment, % of emissions from company-specific reporting.
    • Template 5: accumulated impairment (IFRS-9 has no accumulated-impairment feed on the loan tape).

Chronic vs. acute allocation: the ITS leaves the split to the institution's methodology (Annex XL). We use the
TCFD convention — acute = event-driven perils, chronic = gradual shifts — documented below and overridable.

Template 5 also carries a GEOGRAPHY axis: EBA Q&A 2022_6600 confirms the ITS requires a SEPARATE grid per
geographical area (institutions pick the areas most exposed to physical climate risk), not one portfolio-wide
grid. `template5_grid()` returns the portfolio-wide grid (unchanged shape, for existing consumers) PLUS a
`geographies` breakdown: one NACE-section grid per country, for the countries with the largest exposure (top
10 by gross carrying amount), with the remainder rolled up into an explicit "Other / rest of book" entry so no
exposure silently disappears from the geography axis.
"""
from __future__ import annotations

from services.intelligence.hazard_scope import ACUTE as _HAZARD_ACUTE
from services.intelligence.hazard_scope import CHRONIC as _HAZARD_CHRONIC

# TCFD/EBA physical-climate split. ACUTE = sudden event-driven; CHRONIC = long-term/gradual shifts.
# SOURCED FROM THE SINGLE CLIMATE-HAZARD CLASSIFIER (services.intelligence.hazard_scope) so Template 5 sees
# EVERY climate hazard the engine scores — the full EU-Taxonomy set — not a drifting hardcoded subset. Non-
# climate perils (seismic, volcanic) and out-of-scope pollution are classed 'other' in hazard_scope and so are
# excluded here (Template 5 is climate physical risk only).
# ONE EBA methodology override (ITS Annex XL leaves the split to the institution): coastal flooding / sea-level
# rise is disclosed here as CHRONIC (a gradual sea-level shift), whereas ESRS E1 books the same peril as acute.
_EBA_CHRONIC_OVERRIDE = frozenset({"coastal_flood"})
ACUTE_HAZARDS = frozenset(_HAZARD_ACUTE) - _EBA_CHRONIC_OVERRIDE
CHRONIC_HAZARDS = frozenset(_HAZARD_CHRONIC) | _EBA_CHRONIC_OVERRIDE
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
        if h.get("bucket") not in _HIGH_BUCKETS or h.get("relevant") is False:   # a scale that does not apply to buildings never makes an exposure sensitive
            continue
        hz = h.get("hazard")
        if hz in CHRONIC_HAZARDS:
            chronic = True
        elif hz in ACUTE_HAZARDS:
            acute = True
    return chronic, acute


def _mat_bucket(m: float) -> str:
    return "le5" if m <= 5 else "m5_10" if m <= 10 else "m10_20" if m <= 20 else "gt20"


def _new_mat_ifrs9_row() -> dict:
    """Blank per-row accumulator fields for the maturity-bucket + IFRS-9-staging columns shared by Template 1
    and Template 5. Leading-underscore keys are running sums, stripped before a row is returned to a caller."""
    return {"le5": 0.0, "m5_10": 0.0, "m10_20": 0.0, "gt20": 0.0,
            "_mat_x_gross": 0.0, "_mat_gross": 0.0,
            "stage2": 0.0, "npe": 0.0, "_ifrs9_gross": 0.0}


def _accumulate_mat_ifrs9(row: dict, asset: dict, gross: float) -> tuple[bool, bool]:
    """Adds one exposure's residual-maturity bucket and IFRS-9 stage (each only if the customer supplied it)
    into `row`. Returns (has_maturity, has_ifrs9) so the caller can track book-wide attribute coverage —
    the shared logic behind Template 1's and Template 5's maturity/credit-quality columns.

    Per EBA Q&A 2022_6515: an exposure with no stated maturity BY ITS NATURE (equity, a perpetual
    instrument) must be disclosed in the largest '>20 years' bucket, never silently excluded — that is a
    genuinely different case from simply not having residual_maturity_years supplied yet (still correctly
    excluded/uncovered until the customer provides it). `no_stated_maturity` is the explicit signal
    distinguishing the two; a stated `residual_maturity_years`, if present, always takes precedence over it."""
    has_mat = has_ifrs9 = False
    m = asset.get("residual_maturity_years")
    if m is not None:
        try:
            mv = float(m)
            row[_mat_bucket(mv)] += gross
            row["_mat_x_gross"] += gross * mv
            row["_mat_gross"] += gross
            has_mat = True
        except (TypeError, ValueError):
            pass
    elif asset.get("no_stated_maturity"):
        # no numeric maturity to average into the weighted-average-maturity figure — only the bucket amount
        # is mandated by the Q&A — so _mat_x_gross/_mat_gross are deliberately NOT incremented here.
        row["gt20"] += gross
        has_mat = True
    st = str(asset.get("ifrs9_stage") or "").strip().lower().replace("stage", "").strip()
    if st:
        row["_ifrs9_gross"] += gross
        has_ifrs9 = True
        if st in ("2", "2 "):
            row["stage2"] += gross
        elif st in ("3",):
            row["npe"] += gross
    return has_mat, has_ifrs9


def _mat_avg(r: dict):
    return round(r["_mat_x_gross"] / r["_mat_gross"], 1) if r["_mat_gross"] else None


def _emit_mat_ifrs9(out: dict, r: dict) -> None:
    """Writes the public maturity/IFRS-9 fields (rounded bucket amounts, weighted-average maturity, and the
    per-row coverage flags) onto the emitted row `out`, from the raw accumulator `r`."""
    for k in ("le5", "m5_10", "m10_20", "gt20", "stage2", "npe"):
        out[k] = round(r[k], 2)
    out["avg_maturity"] = _mat_avg(r)
    out["has_maturity"] = r["_mat_gross"] > 0
    out["has_ifrs9"] = r["_ifrs9_gross"] > 0


def template1_grid(assets: list[dict]) -> dict:
    """EBA Pillar 3 Template 1 — banking-book transition-risk exposure by NACE sector (ITS 2022/2453,
    Annex XXXIX / Annex XL). Columns a–p verified verbatim from Annex XL. We COMPUTE the columns our golden
    source supports: (a) gross carrying amount, (i) GHG financed emissions Scope 1+2+3 with (j) of-which
    Scope 3 — using the SAME per-asset ghg figures the platform already sums for financed emissions (no new
    attribution) — and, from the per-loan attributes the customer provides (residual_maturity_years,
    ifrs9_stage — the same fields Template 5 uses), (l–p) maturity buckets + gross-weighted average maturity
    and (f–h) Stage 2 / non-performing. A sector/loan without those attributes stays blank, never fabricated;
    `maturity_covered` / `ifrs9_covered` say whether the book carries them at all. The Paris-benchmark-
    exclusion (b), env-sustainable/aligned (c), accumulated impairment (h) and %-company-reported (k) columns
    are customer/company data we don't hold, declared and left blank."""
    by_sector: dict[str, dict] = {}
    mat_n, ifrs9_n = 0, 0
    for a in assets:
        gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        if not gross:
            continue
        sec = _section(a.get("nace_code"))
        s1, s2, s3 = (a.get("ghg1") or 0), (a.get("ghg2") or 0), (a.get("ghg3") or 0)
        row = by_sector.setdefault(sec, {"section": sec, "label": NACE_SECTIONS.get(sec, "Unclassified"),
                                         "gross": 0.0, "fin_emissions": 0.0, "scope3": 0.0,
                                         **_new_mat_ifrs9_row()})
        row["gross"] += gross
        row["fin_emissions"] += s1 + s2 + s3
        row["scope3"] += s3
        has_mat, has_ifrs9 = _accumulate_mat_ifrs9(row, a, gross)
        mat_n += has_mat
        ifrs9_n += has_ifrs9
    rows = sorted(by_sector.values(), key=lambda r: (r["section"] == "?", r["section"]))
    total = {"section": "TOTAL", "label": "Total", "gross": sum(r["gross"] for r in rows),
             "fin_emissions": sum(r["fin_emissions"] for r in rows), "scope3": sum(r["scope3"] for r in rows)}
    for k in ("le5", "m5_10", "m10_20", "gt20", "stage2", "npe", "_mat_x_gross", "_mat_gross", "_ifrs9_gross"):
        total[k] = sum(r[k] for r in rows)

    def _emit(r):
        out = {k: (round(v) if isinstance(v, float) else v) for k, v in r.items() if not k.startswith("_")}
        _emit_mat_ifrs9(out, r)
        return out

    return {
        "rows": [_emit(r) for r in rows], "total": _emit(total),
        "maturity_covered": mat_n > 0,    # show the maturity columns only when the loan tape carries maturity
        "ifrs9_covered": ifrs9_n > 0,      # show the IFRS-9 columns only when staging is provided
        "customer_columns": ["of which environmentally sustainable / Taxonomy-aligned (CCM)",
                             "of which excluded from EU Paris-aligned Benchmarks",
                             "accumulated impairment",
                             "% of emissions from company-specific reporting"],
        # NOT YET BUILT — column-k formula confirmed in advance by an EBA Q&A sweep: EBA Q&A 2024_7225
        # confirms the denominator for "% of emissions from company-specific reporting" is ALL exposures
        # (GHG-covered or not), never just the GHG-covered subset — the more intuitive-but-wrong reading.
        # Whoever implements this column must divide by the full book, not the covered subset.
        "basis": "Gross carrying amount = outstanding loan balance. Financed emissions (Scope 1+2+3) and of-which "
                 "Scope 3 sum the per-counterparty GHG figures on the book (the platform's financed-emissions "
                 "basis). Maturity buckets + gross-weighted average maturity, and IFRS-9 Stage 2 / non-performing, "
                 "are filled from the loan-tape attributes you provide (residual maturity, IFRS-9 stage); columns "
                 "without that data stay blank. Alignment, Paris-benchmark and accumulated-impairment columns are "
                 "customer-supplied.",
    }


# GAR counterparty classes (Template 7 row axis, mapped from NACE). General government is shown but EXCLUDED
# from the GAR denominator per Art. 7(1) of Del. Reg. (EU) 2021/2178 — but ONLY central governments, central
# banks and supranational issuers are excluded; local/regional government and compulsory social-security
# bodies (also NACE section O) are NOT excluded and stay in scope. Since our book only carries a NACE section
# (not an institutional-sector split), we use the per-loan `counterparty_govt_level` signal the customer can
# supply (central / regional / local) to tell them apart; a NACE-O counterparty without that signal is
# CONSERVATIVELY treated as NOT central (in scope, not excluded) — wrongly excluding it is the bug this fixes,
# so "unknown" must never fall on the excluding side.
_GAR_CENTRAL_LEVELS = frozenset({"central"})


def _gar_counterparty(sec: str, govt_level: str | None = None) -> str:
    if sec == "K":
        return "Financial corporations"
    if sec == "O":
        if (govt_level or "").strip().lower() in _GAR_CENTRAL_LEVELS:
            return "General governments"        # central govt/central bank/supranational — excluded (Art. 7(1))
        return "Non-financial corporations"     # local/regional govt, social security, or unknown — in scope
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
    per-activity objective mapping we don't hold — declared, not fabricated.

    Art. 7(1) excludes ONLY central governments/central banks/supranationals, not local/regional government —
    `_gar_counterparty` uses the per-loan `counterparty_govt_level` to tell them apart, defaulting a NACE-O
    counterparty without that signal to in-scope (never excluded on an unknown/missing signal)."""
    by_cls: dict[str, dict] = {}
    n_nace_o = n_nace_o_signalled = 0
    for a in assets:
        gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        if not gross:
            continue
        sec = _section(a.get("nace_code"))
        govt_level = a.get("counterparty_govt_level")
        if sec == "O":
            n_nace_o += 1
            if (govt_level or "").strip():
                n_nace_o_signalled += 1
        cls = _gar_counterparty(sec, govt_level)
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
    def _r(v):
        return round(v) if isinstance(v, float) else v
    unsignalled_note = (
        f" {n_nace_o - n_nace_o_signalled} of {n_nace_o} public-administration (NACE O) exposures carry no "
        "counterparty_govt_level and are conservatively kept IN SCOPE (not excluded) until the government "
        "level is supplied." if n_nace_o > n_nace_o_signalled else ""
    )
    return {
        "rows": [{k: _r(v) for k, v in r.items()} for r in rows],
        "total_assets": _r(total), "covered_assets": _r(covered), "general_government": _r(govt),
        "eligible": _r(eligible), "aligned": _r(aligned),
        "pct_eligible": round(eligible / covered * 100, 1) if covered else None,
        "gar_stock_pct": round(aligned / covered * 100, 1) if covered else None,
        "govt_level_coverage": {"n_nace_o": n_nace_o, "n_signalled": n_nace_o_signalled},
        "customer_columns": ["CCM / CCA per-objective split (needs per-activity objective mapping)",
                             "GAR on flow (new lending in the period)", "specialised-lending / of-which enabling / transitional"],
        # NOT YET BUILT — formula confirmed in advance by an EBA Q&A sweep so it's built correctly the first
        # time, not guessed: EBA Q&A 2024_7082 confirms the flow-GAR denominator is the gross carrying amount
        # of NEWLY INCURRED exposures during the year, "without deducting the amounts of loan repayments or
        # disposals" — never a period-over-period stock-minus-stock delta (that formula was explicitly
        # rejected by the EBA). Whoever implements "GAR on flow" above must use the new-exposures convention.
        "basis": "Green Asset Ratio on stock = Taxonomy-aligned / covered assets. Covered assets EXCLUDE ONLY "
                 "central governments, central banks and supranational issuers per Art. 7(1) — local/regional "
                 "government and compulsory social-security bodies are NOT excluded and stay in covered assets. "
                 "Scoped by the per-loan counterparty_govt_level (central/regional/local)." + unsignalled_note +
                 " Eligible/aligned read the book's per-asset taxonomy_status (aligned ⊆ eligible); full alignment "
                 "additionally needs the technical screening criteria + DNSH, so an eligibility-only "
                 "classification makes aligned a floor.",
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


_TEMPLATE5_TOP_N_GEOGRAPHIES = 10
_OTHER_GEOGRAPHY = "OTHER"


def _template5_sector_grid(assets: list[dict]) -> dict:
    """The NACE-section × physical-risk grid (gross carrying amount, of-which physical-risk-sensitive,
    chronic/acute/both, maturity buckets, IFRS-9 staging) for one slice of the book. Shared by the
    portfolio-wide grid and each per-geography grid in `template5_grid` — one instance of the computation,
    reused per geography per EBA Q&A 2022_6600."""
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
                                         **_new_mat_ifrs9_row()})
        row["gross"] += gross
        if sensitive:
            row["sensitive"] += gross
        if chronic:
            row["chronic"] += gross
        if acute:
            row["acute"] += gross
        if chronic and acute:
            row["both"] += gross
        has_mat, has_ifrs9 = _accumulate_mat_ifrs9(row, a, gross)
        mat_n += has_mat
        ifrs9_n += has_ifrs9

    rows = sorted(by_sector.values(), key=lambda r: (r["section"] == "?", r["section"]))
    tot = {"section": "TOTAL", "label": "Total"}
    for k in ("gross", "sensitive", "chronic", "acute", "both", "le5", "m5_10", "m10_20", "gt20",
              "stage2", "npe", "_mat_x_gross", "_mat_gross", "_ifrs9_gross"):
        tot[k] = sum(r[k] for r in rows)

    def _emit(r):
        out = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if not k.startswith("_")}
        _emit_mat_ifrs9(out, r)
        return out

    return {"rows": [_emit(r) for r in rows], "total": _emit(tot),
            "maturity_covered": mat_n > 0, "ifrs9_covered": ifrs9_n > 0}


def template5_grid(assets: list[dict]) -> dict:
    """EBA Pillar 3 Template 5 — banking-book physical-risk exposure by NACE sector. Returns the computable
    columns (gross carrying amount, of-which physical-risk-sensitive, chronic, acute, both) per sector + total,
    portfolio-wide (top-level `rows`/`total`, unchanged shape for existing consumers). The maturity buckets and
    IFRS-9 credit-quality columns are filled from the per-loan attributes the customer provides
    (residual_maturity_years, ifrs9_stage) where present; sectors/columns without that data stay blank.

    EBA Q&A 2022_6600 confirms Template 5 needs a SEPARATE grid per geographical area, not one portfolio-wide
    grid — `geographies` gives one NACE-section grid per country, for the top """ + str(_TEMPLATE5_TOP_N_GEOGRAPHIES) + """ countries
    by gross carrying amount, with the rest rolled into an explicit "Other / rest of book" entry so no exposure
    silently disappears from the geography axis."""
    portfolio = _template5_sector_grid(assets)

    country_val: dict[str, float] = {}
    by_country: dict[str, list[dict]] = {}
    for a in assets:
        gross = a.get("outstanding_loan_balance_eur") or a.get("value_eur") or 0
        if not gross:
            continue
        c = (a.get("country") or "").strip().upper() or "?"
        country_val[c] = country_val.get(c, 0.0) + gross
        by_country.setdefault(c, []).append(a)

    top_countries = [c for c, _ in sorted(country_val.items(), key=lambda kv: -kv[1])[:_TEMPLATE5_TOP_N_GEOGRAPHIES]]
    geographies = []
    for c in top_countries:
        g = _template5_sector_grid(by_country[c])
        geographies.append({"country": c, "label": "Unclassified geography" if c == "?" else c,
                            "exposure_eur": round(country_val[c], 2), **g})
    other_countries = [c for c in country_val if c not in top_countries]
    if other_countries:
        other_assets = [a for c in other_countries for a in by_country[c]]
        g = _template5_sector_grid(other_assets)
        geographies.append({"country": _OTHER_GEOGRAPHY, "label": "Other / rest of book",
                            "exposure_eur": round(sum(country_val[c] for c in other_countries), 2), **g})

    return {
        **portfolio,
        "geographies": geographies,
        # any official column still unsourced is declared, not silently dropped
        "customer_columns": ([] if portfolio["maturity_covered"] and portfolio["ifrs9_covered"] else
                             (["Stage 2 / non-performing (IFRS 9)"] if not portfolio["ifrs9_covered"] else []) +
                             (["maturity buckets"] if not portfolio["maturity_covered"] else [])) + ["accumulated impairment"],
        "basis": "Gross carrying amount = outstanding loan balance. 'Of which physical-risk-sensitive' = "
                 "exposures in the top-two severity bands (H/VH). Chronic/acute per the institution's "
                 "methodology (TCFD split). Maturity buckets + IFRS-9 staging are filled from the loan-tape "
                 "attributes you provide (residual maturity, IFRS-9 stage); columns without that data stay blank. "
                 f"Per EBA Q&A 2022_6600 this template also carries a GEOGRAPHY axis (`geographies`): one grid "
                 f"per country, for the top {_TEMPLATE5_TOP_N_GEOGRAPHIES} countries by gross carrying amount, "
                 "plus an 'Other / rest of book' rollup for the remainder.",
    }
