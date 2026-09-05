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
    EUHazard("changing_temperature", T, "Changing temperature", C, SCR, "now",
             "CMIP6 ensemble warming magnitude (projection scenarios)", (H.CHANGING_TEMP,)),
    EUHazard("temperature_variability", T, "Temperature variability", C, SCR, "now",
             "seasonal temperature amplitude + interannual spread (1991–2020 climatology)", (H.TEMP_VARIABILITY,)),
    EUHazard("permafrost_thaw", T, "Permafrost thawing", C, SCR, "now",
             "Obu et al. (2019) permafrost probability (TTOP model, 1 km, NH); thaw-exposure state", (H.PERMAFROST,)),

    # Wind-related (4)
    EUHazard("cyclone", W, "Cyclone / hurricane / typhoon", A, CAL, "now", "storm severity backtest (Spearman 0.47)", (H.STORM,)),
    EUHazard("storm", W, "Storm (blizzard, dust, sand)", A, SCR, "now",
             "ERA5 instantaneous-10 m-wind-gust climatology (1991–2020, stormiest-month peak) — extratropical "
             "windstorms / blizzards / dust-&-sand storms, the wind peril tropical-cyclone models miss (e.g. "
             "European winter windstorms Kyrill/Lothar/Xynthia). Distinct channel from Cyclone.", (H.WINDSTORM,)),
    EUHazard("changing_wind", W, "Changing wind patterns", C, SCR, "now",
             "CMIP6 ensemble |near-surface wind change| (projection scenarios)", (H.CHANGING_WIND,)),
    EUHazard("tornado", W, "Tornado", A, CAL, "now",
             "ERA5 CAPE × 0–6 km shear convective potential (Taszarek 2021 WMAXSHEAR), backtested vs 70k NOAA SPC "
             "tornadoes: ranking AUC 0.73 (EF2+ 0.74), US validation region (scripts/backtest_convective_spc.py); "
             "environment index, also covers large hail / damaging wind", (H.SEVERE_CONVECTIVE,)),

    # Water-related (10)
    EUHazard("drought", WA, "Drought", A, CAL, "now", "multi-belt SPEI backtest", (H.DROUGHT,)),
    EUHazard("flood", WA, "Flood (coastal / fluvial / pluvial / groundwater)", A, SCR, "now",
             "coastal + fluvial live; pluvial P1, groundwater P2", (H.FLOOD, H.COASTAL_FLOOD)),
    EUHazard("water_stress", WA, "Water stress", C, SCR, "now", "partial via soil-water; WRI Aqueduct upgrade P1", (H.SOIL_WATER,)),
    EUHazard("sea_level_rise", WA, "Sea-level rise", C, SCR, "now",
             "IPCC AR6 SLR projection via the coastal-flood freeboard model (elevation + distance-to-coast)", (H.COASTAL_FLOOD,)),
    EUHazard("heavy_precipitation", WA, "Heavy precipitation", A, SCR, "now",
             "wettest-month precip climatology (1991–2020) + CC warming", (H.HEAVY_PRECIP,)),
    EUHazard("saline_intrusion", WA, "Saline intrusion", C, SCR, "now",
             "low-elevation-coastal-zone × AR6 SLR proxy (reuses the coastal DEM + distance-to-coast machinery)", (H.SALINE_INTRUSION,)),
    EUHazard("changing_precipitation", WA, "Changing precipitation patterns", C, SCR, "now",
             "CMIP6 ensemble |precip change| (projection scenarios)", (H.CHANGING_PRECIP,)),
    EUHazard("precipitation_variability", WA, "Precipitation / hydrological variability", C, SCR, "now",
             "rainfall seasonal concentration + interannual spread (1991–2020 climatology)", (H.PRECIP_VARIABILITY,)),
    EUHazard("ocean_acidification", WA, "Ocean acidification", C, SCR, "now",
             "OceanSODA-ETHZ global surface-ocean pH; marine screening for coastal/aquaculture/fisheries exposure (not-applicable for inland land assets)", (H.OCEAN_ACIDIFICATION,)),
    EUHazard("glacial_lake_outburst", WA, "Glacial lake outburst", A, REF, "now",
             "GIGLak global glacial-lake inventory (117k lakes) → size-scaled proximity exposure ZONE. Acute water "
             "hazard (EBA/EU-Taxonomy); a geophysical proximity screen — not a hydraulically-routed inundation nor a "
             "backtestable field (outbursts occur AT mapped lakes, so a proximity backtest is circular). Reference "
             "tier, the same honest posture as volcanic / seismic zones.", (H.GLACIAL_LAKE_OUTBURST,)),

    # Solid-mass-related (7)
    EUHazard("landslide", S, "Landslide", A, CAL, "now",
             "NASA/LHASA global susceptibility, backtested vs the Global Landslide Catalog (9.5k events): "
             "ranking ROC-AUC 0.95, 11× High+ lift (scripts/backtest_landslide_glc.py)", (H.LANDSLIDE,)),
    EUHazard("subsidence", S, "Land subsidence", A, SCR, "now",
             "Herrera-García et al. (2021) Global Subsidence Susceptibility (~1 km, geophysical predisposition)", (H.SUBSIDENCE,)),
    EUHazard("coastal_erosion", S, "Coastal erosion", C, SCR, "now",
             "Vousdoukas et al. (2020, JRC LISCOAST) shoreline-retreat projection (scenario × horizon)", (H.COASTAL_EROSION,)),
    EUHazard("soil_erosion", S, "Soil erosion", C, SCR, "now",
             "GloSEM (Borrelli/Panagos) global cropland soil displacement by water erosion (~100 m, t ha⁻¹ yr⁻¹)", (H.SOIL_EROSION,)),
    EUHazard("soil_degradation", S, "Soil degradation", C, SCR, "now",
             "UNCCD SDG 15.3.1 degraded-land status (Trends.Earth, ESA-CCI + productivity + SoilGrids), read on demand from the COG", (H.SOIL_DEGRADATION,)),
    EUHazard("avalanche", S, "Avalanche", A, SCR, "now",
             "terrain release-angle (on-demand DEM slope) × elevation/latitude snow-climate proxy", (H.AVALANCHE,)),
    EUHazard("solifluction", S, "Solifluction", C, SCR, "now",
             "Obu (2019) permafrost probability × gentle-slope window (derived periglacial susceptibility)", (H.SOLIFLUCTION,)),
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
