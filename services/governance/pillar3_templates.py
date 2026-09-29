"""EBA Pillar 3 ESG — shared pieces of the quantitative templates.

  the physical-risk hazard split  chronic vs acute, from the platform's one climate-hazard classifier (the institution's
                                  documented methodology; Annex XL leaves the split to it)
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
