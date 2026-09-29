"""EBA Pillar 3 ESG — shared pieces of the quantitative templates.

  the physical-risk hazard split  chronic vs acute, from the platform's one climate-hazard classifier (the institution's
                                  documented methodology; Annex XL leaves the split to it)
  gar_grid                        the Green Asset Ratio (Templates 6-8)
  concentration_split             decision / concentration measures over the same book

Templates 1 and 5 are built to the governing template specification in services/governance/pillar3_grids.py.
"""
from __future__ import annotations

from services.intelligence.hazard_scope import ACUTE as _HAZARD_ACUTE
from services.intelligence.hazard_scope import CHRONIC as _HAZARD_CHRONIC
from services.reference import nace as _nace

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

# NACE section (letter) → official title, and code → section: from the platform's ONE NACE reference (Eurostat's
# official NACE Rev. 2 code list — services/reference/nace.py), not a copy kept here. Template 5 rows are by sector.
NACE_SECTIONS: dict[str, str] = _nace.section_labels()


def _section(nace_code) -> str:
    """The section letter of a NACE code in any usual form ('01.11', 'C24', 'A'); '?' when unclassified."""
    return _nace.section(nace_code) or "?"


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


# the regulation's "high impact climate sectors" (SFDR RTS Annex I definition (9)) — the one reference set.
HIGH_CLIMATE_NACE = _nace.sector_set("high_impact_climate_sectors")      # cited in data/reference/nace_sector_sets.json


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
