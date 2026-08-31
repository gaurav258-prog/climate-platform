"""
Canonical vocabulary for the Climate Intelligence Platform.

THIS IS THE SINGLE SOURCE OF TRUTH for every controlled term used across the
stack: hazard types, climate scenarios, time horizons, risk buckets and risk
nature. Three layers must agree on these terms:

  1. Ingestion + scoring (Python)      — import these enums directly.
  2. The database (Postgres)           — CHECK constraints generated from
                                         `*_VALUES` lists (see migration
                                         `b7c1..._vocabulary_constraints`).
  3. The UI (JavaScript)               — mirrors this file in
                                         `ui/src/constants/vocabulary.js`.

Historically each layer drifted into its own dialect (NGFS vs IPCC scenarios,
`heat` vs `heat_acute`, `short_term` vs `2030`). The `normalize_*` functions
below map every known dialect back to the canonical value so nothing downstream
ever has to guess. Unknown values raise `ValueError` — drift fails loudly
instead of silently.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "HazardType",
    "RiskScenario",
    "RiskBucket",
    "RiskNature",
    "TimeHorizon",
    "HAZARD_VALUES",
    "SCENARIO_VALUES",
    "TIME_HORIZON_VALUES",
    "RISK_BUCKET_VALUES",
    "RISK_NATURE_VALUES",
    "normalize_hazard",
    "normalize_scenario",
    "normalize_time_horizon",
    "score_to_bucket",
]


# ─────────────────────────────────────────────────────────────────────────────
# Canonical enums
# ─────────────────────────────────────────────────────────────────────────────

class HazardType(str, Enum):
    FLOOD = "flood"
    COASTAL_FLOOD = "coastal_flood"
    HEAT_ACUTE = "heat_acute"
    HEAT_CHRONIC = "heat_chronic"
    WILDFIRE = "wildfire"
    DROUGHT = "drought"
    STORM = "storm"
    SEISMIC = "seismic"
    VOLCANIC = "volcanic"
    POLLUTION = "pollution"
    FROST = "frost"
    # Root-zone water stress from the soil-moisture anomaly — a DIFFERENT channel from
    # meteorological drought (SPEI): it sees antecedent/deep soil water a rainfall index misses,
    # and is the validated driver for dryland cereals (Spanish durum wheat). Kept as its own
    # hazard_type, not blended into drought, so a cell can carry both (olive→drought, wheat→soil_water).
    SOIL_WATER = "soil_water"
    # Extreme-rainfall exposure (acute) — EU Taxonomy "heavy precipitation". Screening-tier indicator
    # from the wettest-month precipitation climatology + its variability (climatology_baseline, 1991–2020),
    # intensified for warming via Clausius–Clapeyron (~7%/°C). Distinct from FLOOD (the routed/inundation
    # consequence): this is the rainfall driver itself, answerable anywhere the climatology has coverage.
    HEAVY_PRECIP = "heavy_precip"


class RiskScenario(str, Enum):
    """
    NGFS scenario archetypes — the regulatory standard referenced by TCFD,
    ECB and Basel III. IPCC SSP labels (1.5c / 2c / 4c) map in as aliases.
    """
    BASELINE = "baseline"
    ORDERLY_1_5C = "orderly_1_5c"
    DISORDERLY_2C = "disorderly_2c"
    HOT_HOUSE_3_5C = "hot_house_3_5c"


class RiskBucket(str, Enum):
    L = "L"
    M = "M"
    H = "H"
    VH = "VH"


class RiskNature(str, Enum):
    ACUTE = "acute"
    CHRONIC = "chronic"


class TimeHorizon(str, Enum):
    CURRENT = "current"
    Y2030 = "2030"
    Y2050 = "2050"
    Y2100 = "2100"


# ─────────────────────────────────────────────────────────────────────────────
# Canonical value lists (consumed by the DB constraint migration + UI mirror)
# ─────────────────────────────────────────────────────────────────────────────

HAZARD_VALUES: tuple[str, ...] = tuple(h.value for h in HazardType)
SCENARIO_VALUES: tuple[str, ...] = tuple(s.value for s in RiskScenario)
TIME_HORIZON_VALUES: tuple[str, ...] = tuple(t.value for t in TimeHorizon)
RISK_BUCKET_VALUES: tuple[str, ...] = tuple(b.value for b in RiskBucket)
RISK_NATURE_VALUES: tuple[str, ...] = tuple(n.value for n in RiskNature)


# ─────────────────────────────────────────────────────────────────────────────
# Risk bucket thresholds — the one place score→bucket is defined
# ─────────────────────────────────────────────────────────────────────────────

# (inclusive lower bound, exclusive upper bound) on a 0–100 score
_BUCKET_THRESHOLDS: tuple[tuple[float, float, RiskBucket], ...] = (
    (0.0, 25.0, RiskBucket.L),
    (25.0, 50.0, RiskBucket.M),
    (50.0, 75.0, RiskBucket.H),
    (75.0, 100.0001, RiskBucket.VH),
)


def score_to_bucket(score: float) -> RiskBucket:
    """Map a 0–100 canonical risk score to its bucket. Single definition."""
    if score < 0 or score > 100:
        raise ValueError(f"risk score out of range [0, 100]: {score}")
    for lo, hi, bucket in _BUCKET_THRESHOLDS:
        if lo <= score < hi:
            return bucket
    return RiskBucket.VH  # score == 100


# ─────────────────────────────────────────────────────────────────────────────
# Dialect aliases — every known legacy / UI / SQL term → canonical value
# ─────────────────────────────────────────────────────────────────────────────

def _key(raw: str) -> str:
    """Normalize an input token: lowercase, trim, collapse separators."""
    return (
        raw.strip().lower()
        .replace(" ", "_").replace("-", "_").replace(".", "_")
        .replace("__", "_")
    )


_HAZARD_ALIASES: dict[str, HazardType] = {
    # flood
    "flood": HazardType.FLOOD, "flooding": HazardType.FLOOD,
    "river_flood": HazardType.FLOOD, "fluvial": HazardType.FLOOD,
    "pluvial": HazardType.FLOOD, "urban_flood": HazardType.FLOOD,
    # coastal flood / sea-level rise — its own hazard (sea-driven), distinct from rain-driven flood
    "coastal_flood": HazardType.COASTAL_FLOOD, "sea_level": HazardType.COASTAL_FLOOD,
    "sea_level_rise": HazardType.COASTAL_FLOOD, "slr": HazardType.COASTAL_FLOOD,
    "storm_surge": HazardType.COASTAL_FLOOD, "coastal": HazardType.COASTAL_FLOOD,
    # heat (acute is the default for bare "heat")
    "heat": HazardType.HEAT_ACUTE, "heat_acute": HazardType.HEAT_ACUTE,
    "heat_stress": HazardType.HEAT_ACUTE, "heatwave": HazardType.HEAT_ACUTE,
    "heat_wave": HazardType.HEAT_ACUTE, "extreme_heat": HazardType.HEAT_ACUTE,
    "extreme_heat_waves": HazardType.HEAT_ACUTE,
    "heat_chronic": HazardType.HEAT_CHRONIC, "chronic_heat": HazardType.HEAT_CHRONIC,
    # wildfire
    "wildfire": HazardType.WILDFIRE, "fire": HazardType.WILDFIRE,
    "bushfire": HazardType.WILDFIRE, "forest_fire": HazardType.WILDFIRE,
    # drought (meteorological — rainfall deficit, SPEI)
    "drought": HazardType.DROUGHT, "water_stress": HazardType.DROUGHT,
    # soil water (root-zone moisture — a distinct, deeper signal; the dryland-cereal driver)
    "soil_water": HazardType.SOIL_WATER, "soil_moisture": HazardType.SOIL_WATER,
    "root_zone_water": HazardType.SOIL_WATER,
    # storm
    "storm": HazardType.STORM, "extreme_weather": HazardType.STORM,
    "cyclone": HazardType.STORM, "hurricane": HazardType.STORM,
    "typhoon": HazardType.STORM, "hail": HazardType.STORM, "wind": HazardType.STORM,
    # seismic
    "seismic": HazardType.SEISMIC, "earthquake": HazardType.SEISMIC,
    "quake": HazardType.SEISMIC,
    # volcanic
    "volcanic": HazardType.VOLCANIC, "volcanism": HazardType.VOLCANIC,
    "eruption": HazardType.VOLCANIC, "ashfall": HazardType.VOLCANIC,
    "volcano": HazardType.VOLCANIC,
    # pollution
    "pollution": HazardType.POLLUTION, "air_pollution": HazardType.POLLUTION,
    "air_quality": HazardType.POLLUTION, "aqi": HazardType.POLLUTION,
    "smog": HazardType.POLLUTION,

    "frost": HazardType.FROST, "cold": HazardType.FROST, "freeze": HazardType.FROST,
    "extreme_cold": HazardType.FROST, "cold_wave": HazardType.FROST, "frost_days": HazardType.FROST,
    # heavy precipitation / extreme rainfall (the driver, not the flood consequence)
    "heavy_precip": HazardType.HEAVY_PRECIP, "heavy_precipitation": HazardType.HEAVY_PRECIP,
    "extreme_rainfall": HazardType.HEAVY_PRECIP, "extreme_precipitation": HazardType.HEAVY_PRECIP,
    "heavy_rain": HazardType.HEAVY_PRECIP, "intense_rainfall": HazardType.HEAVY_PRECIP,
}

_SCENARIO_ALIASES: dict[str, RiskScenario] = {
    # baseline
    "baseline": RiskScenario.BASELINE, "current_policies": RiskScenario.BASELINE,
    "now": RiskScenario.BASELINE,
    # orderly / 1.5°C / Paris / SSP1-2.6
    "orderly_1_5c": RiskScenario.ORDERLY_1_5C, "orderly": RiskScenario.ORDERLY_1_5C,
    "1_5c": RiskScenario.ORDERLY_1_5C, "15c": RiskScenario.ORDERLY_1_5C,
    "paris": RiskScenario.ORDERLY_1_5C, "paris_aligned": RiskScenario.ORDERLY_1_5C,
    "1_5c_paris_aligned": RiskScenario.ORDERLY_1_5C,
    "ssp1_2_6": RiskScenario.ORDERLY_1_5C, "ssp126": RiskScenario.ORDERLY_1_5C,
    "net_zero": RiskScenario.ORDERLY_1_5C, "net_zero_2050": RiskScenario.ORDERLY_1_5C,
    # disorderly / 2°C / SSP2-4.5
    "disorderly_2c": RiskScenario.DISORDERLY_2C, "disorderly": RiskScenario.DISORDERLY_2C,
    "2c": RiskScenario.DISORDERLY_2C, "2_0c": RiskScenario.DISORDERLY_2C,
    "2c_moderate_transition": RiskScenario.DISORDERLY_2C,
    "moderate": RiskScenario.DISORDERLY_2C,
    "ssp2_4_5": RiskScenario.DISORDERLY_2C, "ssp245": RiskScenario.DISORDERLY_2C,
    # hot house / 3.5–4°C / BAU / SSP5-8.5
    "hot_house_3_5c": RiskScenario.HOT_HOUSE_3_5C, "hot_house": RiskScenario.HOT_HOUSE_3_5C,
    "hothouse": RiskScenario.HOT_HOUSE_3_5C, "3_5c": RiskScenario.HOT_HOUSE_3_5C,
    "4c": RiskScenario.HOT_HOUSE_3_5C, "4_0c": RiskScenario.HOT_HOUSE_3_5C,
    "4c_business_as_usual": RiskScenario.HOT_HOUSE_3_5C,
    "business_as_usual": RiskScenario.HOT_HOUSE_3_5C, "bau": RiskScenario.HOT_HOUSE_3_5C,
    "ssp5_8_5": RiskScenario.HOT_HOUSE_3_5C, "ssp585": RiskScenario.HOT_HOUSE_3_5C,
}

_TIME_HORIZON_ALIASES: dict[str, TimeHorizon] = {
    "current": TimeHorizon.CURRENT, "now": TimeHorizon.CURRENT,
    "baseline": TimeHorizon.CURRENT, "spot": TimeHorizon.CURRENT,
    "short_term": TimeHorizon.Y2030, "short": TimeHorizon.Y2030,
    "near_term": TimeHorizon.Y2030, "2030": TimeHorizon.Y2030,
    "medium_term": TimeHorizon.Y2050, "medium": TimeHorizon.Y2050,
    "mid_term": TimeHorizon.Y2050, "2050": TimeHorizon.Y2050,
    "long_term": TimeHorizon.Y2100, "long": TimeHorizon.Y2100,
    "far_term": TimeHorizon.Y2100, "2100": TimeHorizon.Y2100,
}


# ─────────────────────────────────────────────────────────────────────────────
# Normalizers — the public entry points. Map any dialect → canonical enum.
# ─────────────────────────────────────────────────────────────────────────────

def normalize_hazard(raw: str) -> HazardType:
    """Map any known hazard dialect to the canonical HazardType. Raise on unknown."""
    try:
        return _HAZARD_ALIASES[_key(raw)]
    except KeyError:
        raise ValueError(
            f"unknown hazard '{raw}'. Canonical values: {HAZARD_VALUES}"
        ) from None


def normalize_scenario(raw: str) -> RiskScenario:
    """Map any known scenario dialect (NGFS, IPCC SSP, UI labels) to canonical."""
    try:
        return _SCENARIO_ALIASES[_key(raw)]
    except KeyError:
        raise ValueError(
            f"unknown scenario '{raw}'. Canonical values: {SCENARIO_VALUES}"
        ) from None


def normalize_time_horizon(raw: str) -> TimeHorizon:
    """Map any known time-horizon dialect to canonical (current/2030/2050/2100)."""
    try:
        return _TIME_HORIZON_ALIASES[_key(raw)]
    except KeyError:
        raise ValueError(
            f"unknown time horizon '{raw}'. Canonical values: {TIME_HORIZON_VALUES}"
        ) from None
