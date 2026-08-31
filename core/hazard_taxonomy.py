"""The EU Taxonomy hazard checklist — our coverage of it, stamped with an honest maturity tier.

THIS IS THE SINGLE SOURCE OF TRUTH for how the platform maps onto the 28 physical climate hazards defined by
the EU Taxonomy Climate Delegated Act (Regulation 2021/2139, Annex — Appendix A: "Classification of climate-
related hazards"). A supervisor, an auditor, or a bank's own model team scores climate-risk coverage against
*that* list, so we carry it verbatim and record, per hazard:

  • which of our internal `HazardType` channels serve it (possibly none yet), and
  • a MATURITY TIER — the load-bearing honesty distinction:

      CALIBRATED  the channel is backtested and passes the honesty gate (publishes scores / € figures)
      SCREENING   a real authoritative EO/agency indicator, disclosed as "indicator, not yet calibrated"
      REFERENCE   a static hazard-zone / geophysical layer where a climate projection doesn't apply
      ROADMAP     not built yet — a planned channel, shown so coverage is honest about its gaps

"Coverage" and "calibration" are DIFFERENT claims. This registry lets us say "all 28 are on the map" while
always showing which tier each one sits at — a channel only moves up a tier when it earns it (see
`services/validation`). Adding/upgrading a hazard = editing one row here; nothing downstream guesses.

Phases (P1–P4) come from the coverage roadmap (docs/board/path_to_28.html) and order the ROADMAP rows by
relevance × data-feasibility, not by calendar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from core.types import HazardType

__all__ = [
    "MaturityTier",
    "HazardFamily",
    "EUHazard",
    "EU_TAXONOMY",
    "EXTRA_CHANNELS",
    "eu_hazards_by_family",
    "coverage_summary",
]


class MaturityTier(str, Enum):
    CALIBRATED = "calibrated"   # backtested, passes the honesty gate
    SCREENING = "screening"     # authoritative indicator, disclosed as not-yet-calibrated
    REFERENCE = "reference"     # zone / geophysical layer, no climate projection
    ROADMAP = "roadmap"         # planned, not built yet


class HazardFamily(str, Enum):
    TEMPERATURE = "temperature"
    WIND = "wind"
    WATER = "water"
    SOLID_MASS = "solid_mass"


# a stable id per EU hazard so the UI and any downstream reference it without string-matching the name
@dataclass(frozen=True)
class EUHazard:
    id: str
    family: HazardFamily
    name: str
    nature: str                       # "acute" | "chronic" (per Appendix A)
    tier: MaturityTier
    phase: str                        # "now" (live) | "p1".."p4" (roadmap phase)
    source: str                       # short data-source / status note (honest)
    internal: tuple[HazardType, ...] = field(default_factory=tuple)  # our channel(s) serving it


A, C = "acute", "chronic"
T, W, WA, S = (
    HazardFamily.TEMPERATURE, HazardFamily.WIND, HazardFamily.WATER, HazardFamily.SOLID_MASS,
)
CAL, SCR, REF, ROAD = (
    MaturityTier.CALIBRATED, MaturityTier.SCREENING, MaturityTier.REFERENCE, MaturityTier.ROADMAP,
)
H = HazardType


# ── The 28, verbatim from Appendix A, in its four families ───────────────────────────────────────────────
EU_TAXONOMY: tuple[EUHazard, ...] = (
    # Temperature-related (7)
    EUHazard("heat_wave", T, "Heat wave", A, CAL, "now", "agri heat channel (W-Africa cocoa, ρ 0.60)", (H.HEAT_ACUTE,)),
    EUHazard("heat_stress", T, "Heat stress", C, SCR, "now", "chronic-heat exposure channel", (H.HEAT_CHRONIC,)),
    EUHazard("cold_wave_frost", T, "Cold wave / frost", A, SCR, "now", "global frost baseline (3.1M rows)", (H.FROST,)),
    EUHazard("wildfire", T, "Wildfire", A, SCR, "now", "on-demand, global", (H.WILDFIRE,)),
    EUHazard("changing_temperature", T, "Changing temperature", C, ROAD, "p3", "→ Screening · reanalysis / CMIP6 trend"),
    EUHazard("temperature_variability", T, "Temperature variability", C, ROAD, "p3", "→ Screening · trend indicator"),
    EUHazard("permafrost_thaw", T, "Permafrost thawing", C, ROAD, "p4", "→ Reference · ESA CCI, high-latitude"),

    # Wind-related (4)
    EUHazard("cyclone", W, "Cyclone / hurricane / typhoon", A, CAL, "now", "storm severity backtest (Spearman 0.47)", (H.STORM,)),
    EUHazard("storm", W, "Storm (blizzard, dust, sand)", A, SCR, "now", "global", (H.STORM,)),
    EUHazard("changing_wind", W, "Changing wind patterns", C, ROAD, "p3", "→ Screening · trend indicator"),
    EUHazard("tornado", W, "Tornado", A, ROAD, "p4", "→ Reference · regional catalogues"),

    # Water-related (10)
    EUHazard("drought", WA, "Drought", A, CAL, "now", "multi-belt SPEI backtest", (H.DROUGHT,)),
    EUHazard("flood", WA, "Flood (coastal / fluvial / pluvial / groundwater)", A, SCR, "now",
             "coastal + fluvial live; pluvial P1, groundwater P2", (H.FLOOD, H.COASTAL_FLOOD)),
    EUHazard("water_stress", WA, "Water stress", C, SCR, "now", "partial via soil-water; WRI Aqueduct upgrade P1", (H.SOIL_WATER,)),
    EUHazard("sea_level_rise", WA, "Sea-level rise", C, ROAD, "p1", "→ Screening · Copernicus altimetry (completes coastal)"),
    EUHazard("heavy_precipitation", WA, "Heavy precipitation", A, ROAD, "p1", "→ Screening · ERA5 / IMERG"),
    EUHazard("saline_intrusion", WA, "Saline intrusion", C, ROAD, "p2", "→ Screening · coastal, regional"),
    EUHazard("changing_precipitation", WA, "Changing precipitation patterns", C, ROAD, "p3", "→ Screening · trend indicator"),
    EUHazard("precipitation_variability", WA, "Precipitation / hydrological variability", C, ROAD, "p3", "→ Screening · trend indicator"),
    EUHazard("ocean_acidification", WA, "Ocean acidification", C, ROAD, "p4", "→ Reference · marine, niche"),
    EUHazard("glacial_lake_outburst", WA, "Glacial lake outburst", A, ROAD, "p4", "→ Reference · regional"),

    # Solid-mass-related (7)
    EUHazard("landslide", S, "Landslide", A, ROAD, "p1", "→ Screening · NASA susceptibility"),
    EUHazard("subsidence", S, "Land subsidence", A, ROAD, "p1", "→ Screening · Copernicus EGMS (InSAR)"),
    EUHazard("coastal_erosion", S, "Coastal erosion", C, ROAD, "p2", "→ Screening · satellite shoreline"),
    EUHazard("soil_erosion", S, "Soil erosion", C, ROAD, "p2", "→ Screening · ESDAC / RUSLE (ESRS E4)"),
    EUHazard("soil_degradation", S, "Soil degradation", C, ROAD, "p2", "→ Screening · ESDAC (ESRS E4)"),
    EUHazard("avalanche", S, "Avalanche", A, ROAD, "p4", "→ Reference · mountain, regional"),
    EUHazard("solifluction", S, "Solifluction", C, ROAD, "p4", "→ Reference · niche"),
)

# Channels we carry that sit OUTSIDE the EU climate list (geophysical / nature) — coverage beyond Appendix A.
EXTRA_CHANNELS: tuple[EUHazard, ...] = (
    EUHazard("seismic", S, "Seismic (earthquake)", A, CAL, "now", "USGS/EMSC backtest (Spearman 0.81, AUC 0.96)", (H.SEISMIC,)),
    EUHazard("volcanic", S, "Volcanic", A, REF, "now", "geophysical hazard-zone (any-address gap)", (H.VOLCANIC,)),
    EUHazard("pollution", WA, "Pollution / air quality", C, SCR, "now", "nature channel, disclosed thin", (H.POLLUTION,)),
)


def eu_hazards_by_family() -> dict[str, list[EUHazard]]:
    """The 28, grouped by family in Appendix-A order."""
    out: dict[str, list[EUHazard]] = {f.value: [] for f in HazardFamily}
    for h in EU_TAXONOMY:
        out[h.family.value].append(h)
    return out


def coverage_summary() -> dict:
    """Honest counts: how many of the 28 are covered today, at what tiers, and how many remain on the roadmap."""
    live = [h for h in EU_TAXONOMY if h.phase == "now"]
    roadmap = [h for h in EU_TAXONOMY if h.phase != "now"]
    by_tier: dict[str, int] = {t.value: 0 for t in MaturityTier}
    for h in EU_TAXONOMY:
        by_tier[h.tier.value] += 1
    by_phase: dict[str, int] = {}
    for h in roadmap:
        by_phase[h.phase] = by_phase.get(h.phase, 0) + 1
    return {
        "total": len(EU_TAXONOMY),
        "covered": len(live),
        "roadmap": len(roadmap),
        "by_tier": by_tier,
        "by_phase": by_phase,
        "extra_channels": len(EXTRA_CHANNELS),
    }
