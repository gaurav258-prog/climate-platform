"""Where each calibrated hazard is actually validated — region-aware evidence behind the maturity tier.

`core/hazard_taxonomy.py` says WHETHER a hazard earned CALIBRATED. This module says WHERE. A tier with no region is
a claim of unbounded scope, and skill measured over Europe and the US does not transfer by assertion — the drought
channel, for instance, passes in 9 of 21 crop-regions and fails in the rest. So every CALIBRATED hazard must declare
the macro-regions it was judged in, with the ledger scope it comes from, and its scope claim is DERIVED by the
pre-registered rule in `core/validation_gates.py`, never typed in:

  global         validated (status 'validated', not 'mixed') in >= GLOBAL_CLAIM_MIN_REGIONS macro-regions, at least
                 one of them outside the Global North (latin_america_caribbean / africa / asia)
  pooled_global  validated on a globally distributed target, but the per-region breakdown is not yet reported
  multi_region   validated in >= 2 macro-regions (or validated in one and mixed in others)
  regional       validated in exactly one macro-region
  none           no macro-region validated

Numbers below are copied from the validation ledger (`validation_run`, latest row per hazard/scope/method); a region
absent from a hazard's list is UNTESTED, not "fine". Editing this file is how the claim moves — and the unit tests
force every CALIBRATED hazard to have an entry here.
"""
from __future__ import annotations

from dataclasses import dataclass

from core import validation_gates as G

VALIDATED, MIXED, FAILS = "validated", "mixed", "fails"


@dataclass(frozen=True)
class RegionEvidence:
    region: str        # one of G.MACRO_REGIONS
    status: str        # validated | mixed | fails
    ledger: str        # the validation_run scope label the numbers come from
    evidence: str      # the measured result, in words


REGIONAL_EVIDENCE: dict[str, tuple[RegionEvidence, ...]] = {
    "heat_wave": (
        RegionEvidence("africa", VALIDATED, "agri_temp/west_africa_cocoa", "ρ 0.60 (n=34 yrs) vs observed cocoa production; cocoa only"),
        RegionEvidence("europe", FAILS, "agri_temp/bordeaux_wine", "ρ 0.01 (n=34 yrs) vs wine-grape yield — no heat signal"),
    ),
    "heat_stress": (
        RegionEvidence("europe", VALIDATED, "EU", "ρ 0.85 (n=115 stations)"),
        RegionEvidence("north_america", VALIDATED, "US", "ρ 0.91 (n=133 stations)"),
    ),
    "cold_wave_frost": (
        RegionEvidence("europe", VALIDATED, "EU", "cold-wave channel ρ 0.89 (n=115 stations)"),
        RegionEvidence("north_america", VALIDATED, "US", "cold-wave channel ρ 0.86 (n=133 stations)"),
    ),
    "wildfire": (
        RegionEvidence("europe", VALIDATED, "EFFIS 2022–24, held out in time", "occurrence AUC 0.76, magnitude ρ 0.37 (41k burn scars)"),
    ),
    "tornado": (
        RegionEvidence("north_america", VALIDATED, "CONUS", "temporal holdout ρ 0.51, AUC 0.82 (n=23,331)"),
    ),
    "drought": (
        RegionEvidence("oceania", VALIDATED, "agri_spei/australia_wheat", "ρ 0.64 (n=34 yrs)"),
        RegionEvidence("europe", MIXED, "agri_spei/spain_*", "passes for Spain central ρ 0.56 and olive ρ 0.36; fails for sugar beet ρ −0.27"),
        RegionEvidence("africa", MIXED, "agri_spei/{algeria,morocco,tunisia}_wheat, nigeria_sorghum, south_africa_maize",
                       "passes for North-African wheat (ρ 0.47–0.67); fails for Nigeria sorghum ρ 0.18 and South-Africa maize ρ 0.15"),
        RegionEvidence("asia", MIXED, "agri_spei/{iran,kazakhstan,syria,turkey}_wheat, india_rice, india_cane",
                       "passes for West/Central-Asia wheat (ρ 0.40–0.57); fails for India rice ρ 0.19 and cane ρ −0.01"),
        RegionEvidence("north_america", FAILS, "agri_spei/us_cornbelt, canada_prairies", "US Corn Belt ρ −0.06; Canadian prairies ρ 0.22"),
        RegionEvidence("latin_america_caribbean", FAILS, "agri_spei/argentina_wheat, brazil_coffee, brazil_soy",
                       "Argentina wheat ρ 0.09; Brazil coffee ρ −0.43 and soy ρ −0.22"),
    ),
    "flood": (
        RegionEvidence("europe", VALIDATED, "Europe", "Copernicus EMS 2019–24 observed extents: ρ 0.47, AUC 0.84 (n=417 nodes)"),
    ),
    "sea_level_rise": (
        RegionEvidence("north_america", VALIDATED, "US", "NOAA CO-OPS gauges: ρ 0.41 (n=218)"),
    ),
    "heavy_precipitation": (
        RegionEvidence("europe", VALIDATED, "EU", "ρ 0.42 (n=115 stations)"),
        RegionEvidence("north_america", VALIDATED, "US", "ρ 0.70 (n=133 stations)"),
    ),
    "subsidence": (
        RegionEvidence("europe", VALIDATED, "EU", "EGMS InSAR held out in time: ρ 0.85 (200,000 cells)"),
        RegionEvidence("north_america", FAILS, "US", "susceptibility-class test ρ 0.22 (n=4,834) — indicator only"),
    ),
    "cyclone": (
        RegionEvidence("latin_america_caribbean", VALIDATED, "global (storm_oos, stratified)",
                       "held-out IBTrACS seasons 2003+: ρ 0.77 (n=5,973 cells) — the stored storm channel only holds cells in this region; "
                       "Asia/Europe/Oceania have ≤4 cells each, so no other basin is tested yet. Wind intensity, not damage"),
    ),
    "permafrost_thaw": (
        RegionEvidence("europe", VALIDATED, "Europe/Arctic", "GTN-P boreholes: ρ 0.82 (n=229)"),
    ),
}

# Validated on a globally distributed target, per-region breakdown not yet reported. Kept explicit so a pooled global
# number is never silently promoted to a global claim.
POOLED_GLOBAL: dict[str, str] = {
    "sea_level_rise": "GESLA-3 gauges: held out in time ρ 0.92 (n=810), leave-one-gauge-out ρ 0.84 (n=1,778); gauge network is Global-North-heavy; per-region breakdown not yet reported. Still-water level, not inundation.",
    "landslide": "Global Landslide Catalog (AUC 0.95); LHASA used the catalogue in its own development, so this reproduces the published susceptibility's discrimination rather than a fresh held-out test.",
}

CAVEATS: dict[str, str] = {
    "drought": "Skill is regime-specific: it holds for rain-fed winter cereals and tree crops in semi-arid regimes (Mediterranean, "
               "West/Central Asia, Australia) and fails for humid, irrigated and summer crops (US Corn Belt, Brazil, Argentina, "
               "India rice/cane, Nigeria, South Africa). Do not quote it as a general drought score.",
    "subsidence": "Observed InSAR ground motion (EGMS) exists for Europe only; elsewhere the susceptibility class is an indicator.",
    "wildfire": "Validated in Europe; elsewhere the same layer is a screening indicator until tested on North-American and tropical burn records.",
}


def _statuses(hazard_id: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {VALIDATED: [], MIXED: [], FAILS: []}
    for e in REGIONAL_EVIDENCE.get(hazard_id, ()):
        out[e.status].append(e.region)
    return out


def scope_claim(hazard_id: str) -> str:
    """The scope we may claim for a hazard, derived by the pre-registered rule (see module docstring)."""
    st = _statuses(hazard_id)
    v = set(st[VALIDATED])
    if len(v) >= G.GLOBAL_CLAIM_MIN_REGIONS and v & set(G.GLOBAL_CLAIM_MUST_INCLUDE_ONE_OF):
        return "global"
    if hazard_id in POOLED_GLOBAL:
        return "pooled_global"
    if len(v) >= 2 or (len(v) >= 1 and st[MIXED]):
        return "multi_region"
    if len(v) == 1:
        return "regional"
    return "none"


def regional_view(hazard_id: str) -> dict:
    """Serializable region evidence for the coverage API / UI."""
    listed = {e.region for e in REGIONAL_EVIDENCE.get(hazard_id, ())}
    return {
        "scope_claim": scope_claim(hazard_id),
        "regions": [{"region": e.region, "status": e.status, "ledger": e.ledger, "evidence": e.evidence}
                    for e in REGIONAL_EVIDENCE.get(hazard_id, ())],
        "untested_regions": [r for r in G.MACRO_REGIONS if r not in listed],
        "pooled_note": POOLED_GLOBAL.get(hazard_id),
        "caveat": CAVEATS.get(hazard_id),
    }
