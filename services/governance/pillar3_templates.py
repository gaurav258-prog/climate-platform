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

# NACE section (letter) → official title, and code → section: from the platform's ONE NACE reference (Eurostat's
# official NACE Rev. 2 code list — services/reference/nace.py), not a copy kept here. Template 5 rows are by sector.
NACE_SECTIONS: dict[str, str] = _nace.section_labels()


def _section(nace_code) -> str:
    """The section letter of a NACE code in any usual form ('01.11', 'C24', 'A'); '?' when unclassified."""
    return _nace.section(nace_code) or "?"


# Before the stated method (E69, 2026-09-30) every snapshot counted 'at risk' as the High and Very-high score bands —
# score ≥ 50 (core.types.score_to_bucket: M < 50 ≤ H). A snapshot frozen then carries no 'method' record; its figures
# were computed on that definition and are traced and re-rendered on it, never on today's.
LEGACY_LEVEL = 50.0


def stated_level(payload: dict | None) -> float | None:
    """The at-risk level a snapshot's figures were computed on — the institution's method.at_risk_level for the period,
    frozen with the snapshot (payload['method'], services.money.params.Method.record); LEGACY_LEVEL for a snapshot frozen
    before there was a method record. None when the level was not stated."""
    if payload and "method" not in payload:
        return LEGACY_LEVEL
    for u in ((payload or {}).get("method") or {}).get("used") or []:
        if u and u.get("key") == "method.at_risk_level" and u.get("member") is None:
            return float(u["value"])
    return None


def hazard_hit(h: dict, level: float) -> bool:
    """A hazard makes an exposure sensitive when its score is at or above the institution's stated level (Annex XL leaves
    the identification of sensitive exposures to the institution's methodology). A scale that does not apply to the
    exposure (the relevance registry) never does."""
    return h.get("relevant") is not False and h.get("score") is not None and float(h["score"]) >= level


def _asset_hits(asset: dict, level: float) -> tuple[bool, bool]:
    """(chronic_hit, acute_hit) — is this exposure sensitive to a chronic / acute climate peril: any hazard of that
    category at or above the stated level."""
    chronic = acute = False
    for h in asset.get("hazards") or []:
        if not hazard_hit(h, level):
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


def concentration_split(assets: list[dict], level: float | None) -> dict:
    """Decision/concentration measures over the banking book, from the SAME per-asset fields the Pillar 3
    templates use: acute- vs chronic-peril exposure (Template 5 split), and concentration in the EBA high-
    climate-impact NACE sectors (the axis of Templates 1 & 5), with the single most-concentrated sector.
    Acute and chronic overlap where an exposure faces both — they are lenses on the at-risk book, not a
    partition. Measured on the book value (value_eur, the basis of the book total). Without a stated level the acute
    and chronic values are None (a gap)."""
    acute_val = chronic_val = hci_val = 0.0
    sector_val: dict[str, float] = {}
    for a in assets:
        v = a["value_eur"]
        if not v:
            continue
        chronic, acute = _asset_hits(a, level) if level is not None else (False, False)
        if acute:
            acute_val += v
        if chronic:
            chronic_val += v
        sec = _section(a.get("nace_code"))
        sector_val[sec] = sector_val.get(sec, 0.0) + v
        if sec in HIGH_CLIMATE_NACE:
            hci_val += v
    top_sec, top_val = max(sector_val.items(), key=lambda kv: kv[1], default=("?", 0.0))
    return {"acute_val": acute_val if level is not None else None, "chronic_val": chronic_val if level is not None else None,
            "high_climate_val": hci_val,
            "top_sector": top_sec, "top_sector_val": top_val, "by_sector": sector_val}
