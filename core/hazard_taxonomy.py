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
    EUHazard("heat_wave", T, "Heat wave", A, CAL, "now", "agricultural heat channel (West Africa cocoa, rank correlation 0.60)", (H.HEAT_ACUTE,)),
    EUHazard("heat_stress", T, "Heat stress", C, CAL, "now", "observed days ≥ 30 °C from 30 years of daily maxima (NASA POWER); station-validated", (H.HEAT_CHRONIC,)),
    EUHazard("cold_wave_frost", T, "Cold wave / frost", A, CAL, "now", "cold wave: 1-in-10 coldest night vs building thresholds (NASA POWER daily minima), station-validated; frost: global crop-frost baseline (crop scale, screening)", (H.COLD_WAVE, H.FROST)),
    EUHazard("wildfire", T, "Wildfire", A, CAL, "now",
             "Wildfire hazard climatology: Copernicus CEMS/ECMWF Fire Weather "
             "Index extreme-danger days 2006-2020 × burnable-land fraction + C3S ESA-CCI observed burn history 2001-2019, "
             "fixed disclosed formula. Validated on the INDEPENDENT official EFFIS burn record 2022-2024 held out in time "
             "(41k scars, Europe): occurrence AUC 0.76 (2.2× High+ lift), magnitude ρ 0.37 — meets the 0.35 minimum, narrowly; "
             "the fire-weather×fuel term alone is AUC 0.68 / ρ 0.22 (below gate), burn history carries most of the skill "
             "(that term is not fully independent of the validation record, disclosed). Validated in Europe; elsewhere the same layer is a screening indicator. A same-day fire-weather variant did not pass the same test (AUC 0.44) and is not used for scoring.", (H.WILDFIRE,)),
    EUHazard("changing_temperature", T, "Changing temperature", C, SCR, "now",
             "CMIP6 ensemble warming magnitude (projection scenarios)", (H.CHANGING_TEMP,)),
    EUHazard("temperature_variability", T, "Temperature variability", C, SCR, "now",
             "seasonal temperature amplitude + interannual spread (1991–2020 climatology)", (H.TEMP_VARIABILITY,)),
    EUHazard("permafrost_thaw", T, "Permafrost thawing", C, SCR, "now",
             "Obu et al. (2019) permafrost probability (TTOP model, 1 km, NH); thaw-exposure state", (H.PERMAFROST,)),

    # Wind-related (4)
    EUHazard("cyclone", W, "Cyclone / hurricane / typhoon", A, CAL, "now",
             "1-in-10-year Rankine-vortex wind at the cell over 1981+ annual maxima from IBTrACS best-tracks (v3; the earlier "
             "worst-on-record field could not be held out in time). Validated out of time: the score rebuilt from seasons before "
             "a holdout window ranks the observed peak intensity of the later storms with rank correlation 0.78–0.88 across five "
             "windows of ≥10 seasons. A wind-intensity validation, not a damage anchor: observed wind damage or insured loss is "
             "still pending.", (H.STORM,)),
    EUHazard("storm", W, "Storm (blizzard, dust, sand)", A, SCR, "now",
             "ERA5 instantaneous-10 m-wind-gust climatology — extratropical windstorms / blizzards / dust-&-sand "
             "storms, the wind peril tropical-cyclone models miss (e.g. European winter windstorms Kyrill/Lothar/"
             "Xynthia). Distinct channel from Cyclone. Screening ranking only, not calibrated: both the mean-gust "
             "field and an extreme annual-maximum-gust variant (15 years, continental US 2009-2023) fail an independent NOAA "
             "Storm-Events backtest (AUC about 0.5, rank correlation at most 0.20 against the 0.35 minimum): the annual-maximum "
             "10 m gust is dominated by convective and tropical events, not the synoptic windstorm peril. A synoptic-filtered "
             "field is a disclosed planned enhancement.", (H.WINDSTORM,)),
    EUHazard("changing_wind", W, "Changing wind patterns", C, SCR, "now",
             "CMIP6 ensemble |near-surface wind change| (projection scenarios)", (H.CHANGING_WIND,)),
    EUHazard("tornado", W, "Tornado", A, CAL, "now",
             "ERA5 CAPE × 0–6 km shear convective potential (Taszarek 2021 WMAXSHEAR), backtested vs 70k NOAA SPC "
             "tornadoes: ranking AUC 0.73 (EF2+ 0.74), US validation region; environment index, also covers large hail / damaging wind", (H.SEVERE_CONVECTIVE,)),

    # Water-related (10)
    EUHazard("drought", WA, "Drought", A, CAL, "now", "multi-region SPEI drought-index validation", (H.DROUGHT,)),
    EUHazard("flood", WA, "Flood (coastal / fluvial / pluvial / groundwater)", A, SCR, "now",
             "ERA5-Land multi-event model (16 European floods, precip/soil/runoff), coastal + fluvial live; pluvial P1, groundwater "
             "P2. Judged on INDEPENDENT official Copernicus EMS observed flood extents with each of 6 EMS-era floods held out: pooled ROC-AUC 0.68 (5 of 6 events 0.71-0.85; Storm Alex flash flood 0.42), AP 2x base "
             "— real but modest skill; rank correlation 0.17 is below the 0.35 minimum, so the channel is classified Screening rather than Calibrated", (H.FLOOD, H.COASTAL_FLOOD)),
    EUHazard("water_stress", WA, "Water stress", C, SCR, "now", "partial coverage via soil-water; WRI Aqueduct integration planned", (H.SOIL_WATER,)),
    EUHazard("sea_level_rise", WA, "Sea-level rise", C, SCR, "now",
             "IPCC AR6 SLR projection via the coastal-flood freeboard model (elevation + distance-to-coast). Checked against "
             "INDEPENDENT observed NOAA CO-OPS tide-gauge extremes (169 continental-US gauges, 2014-2023): "
             "the generic 2.0 m surge allowance sits at the 80th percentile of observed 10-yr maxima (20% of gauges saw more), "
             "and the score has no site surge/tide term (rank correlation −0.32 against observed extremes). Classified Screening; a site-specific extreme-water-level term is the disclosed gap", (H.COASTAL_FLOOD,)),
    EUHazard("heavy_precipitation", WA, "Heavy precipitation", A, CAL, "now",
             "wettest-month precip climatology (1991–2020) + CC warming; station-validated against observed 1-day maxima", (H.HEAVY_PRECIP,)),
    EUHazard("saline_intrusion", WA, "Saline intrusion", C, SCR, "now",
             "low-elevation-coastal-zone × AR6 SLR proxy (derived from coastal elevation and distance-to-coast data)", (H.SALINE_INTRUSION,)),
    EUHazard("changing_precipitation", WA, "Changing precipitation patterns", C, SCR, "now",
             "CMIP6 ensemble |precip change| (projection scenarios)", (H.CHANGING_PRECIP,)),
    EUHazard("precipitation_variability", WA, "Precipitation / hydrological variability", C, SCR, "now",
             "rainfall seasonal concentration + interannual spread (1991–2020 climatology)", (H.PRECIP_VARIABILITY,)),
    EUHazard("ocean_acidification", WA, "Ocean acidification", C, SCR, "now",
             "OceanSODA-ETHZ global surface-ocean pH; marine screening for coastal/aquaculture/fisheries exposure (not-applicable for inland land assets)", (H.OCEAN_ACIDIFICATION,)),
    EUHazard("glacial_lake_outburst", WA, "Glacial lake outburst", A, REF, "now",
             "GIGLak global glacial-lake inventory (117k lakes) , scored as a size-scaled proximity exposure zone. Acute water "
             "hazard (EBA/EU-Taxonomy); a geophysical proximity screen — not a hydraulically-routed inundation nor a "
             "backtestable field (outbursts occur AT mapped lakes, so a proximity backtest is circular). Reference "
             "tier, the same honest posture as volcanic / seismic zones.", (H.GLACIAL_LAKE_OUTBURST,)),

    # Solid-mass-related (7)
    EUHazard("landslide", S, "Landslide", A, CAL, "now",
             "physical NASA/LHASA susceptibility (terrain/geology, independent of any event catalogue), validated "
             "vs the INDEPENDENT Global Landslide Catalog (9.5k events): ranking ROC-AUC 0.95, 11× High+ lift. Caveat: the LHASA model used this catalogue during its own development, so this reproduces the published susceptibility's discrimination rather than a fresh held-out test.", (H.LANDSLIDE,)),
    EUHazard("subsidence", S, "Land subsidence", A, SCR, "now",
             "Herrera-García et al. (2021) Global Subsidence Susceptibility (~1 km, geophysical predisposition)", (H.SUBSIDENCE,)),
    EUHazard("coastal_erosion", S, "Coastal erosion", C, SCR, "now",
             "Vousdoukas et al. (2020, JRC LISCOAST) shoreline-retreat projection (scenario × horizon)", (H.COASTAL_EROSION,)),
    EUHazard("soil_erosion", S, "Soil erosion", C, SCR, "now",
             "GloSEM (Borrelli/Panagos) global cropland soil displacement by water erosion (~100 m, t ha⁻¹ yr⁻¹)", (H.SOIL_EROSION,)),
    EUHazard("soil_degradation", S, "Soil degradation", C, SCR, "now",
             "UNCCD SDG 15.3.1 degraded-land status (Trends.Earth, ESA-CCI + productivity + SoilGrids), read on demand from the source raster", (H.SOIL_DEGRADATION,)),
    EUHazard("avalanche", S, "Avalanche", A, SCR, "now",
             "terrain release-angle (on-demand DEM slope) × elevation/latitude snow-climate proxy", (H.AVALANCHE,)),
    EUHazard("solifluction", S, "Solifluction", C, SCR, "now",
             "Obu (2019) permafrost probability × gentle-slope window (derived periglacial susceptibility)", (H.SOLIFLUCTION,)),
)

# Channels we carry that sit OUTSIDE the EU climate list (geophysical / nature) — coverage beyond Appendix A.
EXTRA_CHANNELS: tuple[EUHazard, ...] = (
    EUHazard("seismic", S, "Seismic (earthquake)", A, SCR, "now",
             "Bakun-Wentworth IPE on the USGS/EMSC catalogue. Consistency check only (near-field rank correlation 0.81, AUC 0.96): the score is derived from the same catalogue it is checked against (see the Model validation page), so this is not an independent out-of-sample test; one is pending.", (H.SEISMIC,)),
    EUHazard("volcanic", S, "Volcanic", A, SCR, "now",
             "Smithsonian GVP Holocene catalogue (all ~1,200 volcanoes + confirmed-eruption VEI history) scored by "
             "radial proximal+ashfall physics; footprint from a curated hazard map where one exists, else VEI-scaled "
             "defaults (VEI-3 assumed when GVP records none). Radially symmetric (no wind/topography); eruption "
             "recency reported, not weighted. Eruptions are too rare for a location-level occurrence backtest → "
             "classified Screening; no euro figure is published for this hazard.", (H.VOLCANIC,)),
    EUHazard("pollution", WA, "Pollution / air quality", C, SCR, "now", "air-quality screening channel; coverage disclosed as limited", (H.POLLUTION,)),
)


# ── The CALIBRATED gate: independent-target validation is REQUIRED ────────────────────────────────────────
# A hazard may be tiered CALIBRATED ONLY if it is validated against an observed target that is INDEPENDENT of
# the model's own inputs (no in-sample / circular skill — a score built from the same catalogue it is tested
# against does NOT qualify, however strong the near-field consistency). Every CALIBRATED hazard MUST appear
# here, naming its independent target + backtest; a unit test enforces the two-way match,
# so a channel cannot be promoted to CALIBRATED without declaring how it earned it. See [[feedback_no_shortcuts]].
CALIBRATED_VALIDATION: dict[str, dict] = {
    "heat_wave": {"target": "observed cocoa production, FAO/ICCO (independent of ERA5 heat)",
                  "validation": "Cocoa production backtest", "out_of_sample": True},
    "drought": {"target": "observed crop-production shock, FAO (independent of ERA5 SPEI)",
                "validation": "Coffee-region climate backtest", "out_of_sample": True},
    "cyclone": {"target": "NOAA IBTrACS observed peak track intensity (max wind, kt) within 100 km, storm seasons held out in time: the "
                          "predictor is the 1-in-10-year return-level wind rebuilt from seasons BEFORE each window only. Rank correlation "
                          "0.78 (2003+), 0.79 (2010+), 0.86 (2013+), 0.87 (2016+), 0.88 (2017+); windows shorter than the 10-year return period are "
                          "refused by the validator. Same catalogue as the model inputs but the held-out seasons never enter the "
                          "predictor; a wind-intensity validation, not a damage anchor",
                "validation": "IBTrACS temporal-holdout backtest", "out_of_sample": True},
    "tornado": {"target": "NOAA SPC observed tornadoes (independent of the ERA5 CAPE×shear field)",
                "validation": "NOAA SPC tornado backtest", "out_of_sample": True},
    "wildfire": {"target": "official EFFIS burnt-area record 2022-2024 (41k JRC-mapped burn scars, Europe), held out in time: "
                           "every input ends 2020. The fire-weather × fuel term is fully independent; the burn-history term reuses "
                           "the 2001-2019 record and is therefore not fully independent. Rank correlation 0.37 narrowly exceeds "
                           "the 0.35 minimum; Europe only",
                 "validation": "EFFIS burnt-area backtest", "out_of_sample": True},
    "heat_stress": {"target": "NOAA GHCN-Daily station observations 1991–2020: days ≥ 30 °C per year at 248 stations (one per 1° box, Europe + "
                              "contiguous US); stations are independent of the MERRA-2 daily maxima the channel reads. Rank correlation 0.92 "
                              "(EU 0.85, US 0.91), strong. A rank validation of the physical quantity, not a damage anchor",
                    "validation": "GHCN-Daily station backtest", "out_of_sample": True},
    "cold_wave_frost": {"target": "NOAA GHCN-Daily station observations 1991–2020: the 1-in-10 coldest night at 248 stations, independent of the "
                                  "MERRA-2 minima the cold-wave channel reads. Rank correlation 0.89 (EU 0.89, US 0.86), strong. Applies to the "
                                  "cold-wave channel; the frost channel remains a crop scale and is not headline-eligible for buildings",
                        "validation": "GHCN-Daily station backtest", "out_of_sample": True},
    "heavy_precipitation": {"target": "NOAA GHCN-Daily station observations 1991–2020: mean annual maximum 1-day precipitation at 248 stations, "
                                      "independent of the ERA5 monthly climatology the channel reads. Rank correlation 0.69 (US 0.70 strong, EU 0.42 fair)",
                            "validation": "GHCN-Daily station backtest", "out_of_sample": True},
    "landslide": {"target": "NASA Global Landslide Catalog (independent event inventory; physical susceptibility "
                            "inputs). The LHASA model used this catalogue in its development, so this is not a fresh held-out test",
                  "validation": "Global Landslide Catalog backtest", "out_of_sample": False},
}


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
