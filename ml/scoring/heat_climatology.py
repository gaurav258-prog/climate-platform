"""
Heat hazard scoring — transparent, physics-style (two honest components).

The native cocoa backtest (scripts/backtest_cocoa_drought.py) showed the 2023/24 collapse
tracked EXTREME HEAT (2024 = hottest year in 34, +1.16 °C), not drought. So heat is the
validated cocoa signal. The score blends two interpretable parts:

  ABSOLUTE thermal stress (spatial): where the mean temperature sits in cocoa's stress band
      (~25 °C comfortable → ~31 °C severe). Discriminates BY LOCATION.
  ANOMALY (temporal): standardized deviation z from the 1991–2020 normal, clipped. Captures
      an unusually hot YEAR (2024). Discriminates BY TIME.

  heat_score = 100 × clip( W_ABS·abs_stress + W_ANOM·anom , 0, 1)

A pure anomaly-percentile (Φ(z)) was rejected: under the warming trend every cell in 2024 is
many σ above the 1991–2020 mean, so it saturates at 100 everywhere (honest but non-
discriminating). Forward scenarios add a warming delta (°C) to the temperature — physically
grounded, not a flat multiplier. v0: absolute Tmax>32 °C pod-fill thresholds = the refinement.
"""
from __future__ import annotations

import math

# Global-mean warming delta (°C) by NGFS-style scenario at full horizon (2100).
# Applied × horizon fraction. West Africa warms ~1.2–1.4× global; v0 uses global (conservative).
SCENARIO_WARMING_C = {
    "baseline": 0.6, "orderly_1_5c": 1.5, "disorderly_2c": 2.0, "hot_house_3_5c": 3.5,
}
HORIZON_FRACTION = {"current": 0.0, "2030": 0.3, "2050": 0.6, "2100": 1.0}

# --- Regional warming amplification (AR6-grounded, parametric v1) ------------------------------
# SCENARIO_WARMING_C is GLOBAL-MEAN surface warming (land + ocean). Real assets sit on LAND, which
# warms faster than the global mean, and the gap widens toward the poles (Arctic amplification). A
# single global delta therefore UNDER-projects land warming everywhere and mis-ranks a mid-latitude
# belt against a tropical one under the same scenario. We scale the global delta by a smooth
# latitude factor calibrated to IPCC AR6 WGI zonal LAND-warming ratios (× global mean):
#     amp(lat) = LAND_BASE + POLAR_K · (|lat|/90)²   , clipped to [LAND_BASE, AMP_MAX]
# Anchor points this reproduces — equatorial land ~1.40, Mediterranean 37° ~1.65, N-Europe 52° ~1.85,
# sub-Arctic 65° ~2.18. This is a PARAMETRIC shift of today's climatology, honest about land +
# latitude — NOT downscaled CMIP6 (that stays the tracked next step). It does not add the Mediterranean
# summer DRYING hotspot beyond temperature; that is a further refinement, not faked here. lat=None
# falls back to the land-mean (LAND_BASE) — still better than the raw global mean. Current horizon =
# 0 warming, so amplification never touches a live score, only 2030/2050/2100 projections.
LAND_BASE = 1.40   # land warms ~1.4× the global mean (AR6 land–ocean contrast), equatorward floor
POLAR_K = 1.5      # polar-amplification gain across the |lat|/90 span
AMP_MAX = 3.0      # cap (deep-Arctic land tops out near here; keeps the shift bounded)


def warming_amplification(lat: float | None) -> float:
    """Land/latitude warming multiplier on the global-mean delta. lat=None → land-mean floor."""
    if lat is None:
        return LAND_BASE
    return min(AMP_MAX, LAND_BASE + POLAR_K * (abs(lat) / 90.0) ** 2)


def warming_delta(scenario: str = "baseline", horizon: str = "current",
                  lat: float | None = None) -> float:
    """Local land warming °C for a scenario × horizon at latitude `lat`: the global-mean delta
    scaled by the AR6 land/latitude amplification. Current horizon is always 0."""
    global_delta = SCENARIO_WARMING_C.get(scenario, 0.0) * HORIZON_FRACTION.get(horizon, 0.0)
    return global_delta * warming_amplification(lat)


# --- Regional PRECIPITATION decline (AR6, projections v2) --------------------------------------
# v1 dries a forward projection only through TEMPERATURE (more evapotranspiration; DRYING_PER_C in
# the drought/soil_water scorers). It misses the direct PRECIPITATION decline that CMIP6 robustly
# projects for the Mediterranean — the region's defining "hotspot" signal, and the one that matters
# most here because every crop we publish (olive, wheat, barley) sits in it. AR6 WGII CCP4:
# Mediterranean precipitation declines ~4% per 1 °C of GLOBAL warming (high confidence above 2 °C).
# We fold that in as an ADDITIONAL SPEI/soil-moisture drying, applied ONLY where AR6's regional
# precip signal is robust (the Med box) — elsewhere we keep temperature-only rather than invent a
# precipitation trend we can't cite. This is a PARAMETRIC shift grounded in AR6's regional value,
# NOT a raw multi-model CMIP6 download+bias-correction (that remains the tracked next step).
MED_PRECIP_FRAC_PER_C = 0.04   # fractional precip decline per °C GLOBAL warming (AR6 WGII CCP4)
# fractional-precip-change → SPEI z-units: a mean shift of Δ in a distribution with coefficient of
# variation CV moves the standardized index by Δ/CV. Med seasonal precip CV ≈ 0.33, so ≈ 1/0.33.
# Conservative parametric v1 (same class of assumption as DRYING_PER_C); stated, not hidden.
PRECIP_FRAC_TO_SPEI = 3.0
_MED_BOX = (28.0, 47.0, -10.0, 45.0)   # lat_min, lat_max, lon_min, lon_max — AR6 Mediterranean region


def _in_mediterranean(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    la0, la1, lo0, lo1 = _MED_BOX
    return la0 <= lat <= la1 and lo0 <= lon <= lo1


def precip_drying_spei(scenario: str = "baseline", horizon: str = "current",
                       lat: float | None = None, lon: float | None = None) -> float:
    """Extra SPEI/soil-moisture drying from the AR6 regional PRECIPITATION decline (0 outside the
    robust Mediterranean signal, 0 at the current horizon). Uses the GLOBAL-mean warming (the AR6
    %/°C is stated per global °C), NOT the land/latitude-amplified local warming."""
    if not _in_mediterranean(lat, lon):
        return 0.0
    global_delta = SCENARIO_WARMING_C.get(scenario, 0.0) * HORIZON_FRACTION.get(horizon, 0.0)
    return global_delta * MED_PRECIP_FRAC_PER_C * PRECIP_FRAC_TO_SPEI


# Cocoa thermal-stress band (mean-temperature proxy, °C) and blend weights.
T_COMFORT, T_SEVERE = 25.0, 31.0
Z_FULL = 3.0        # anomaly z at which the temporal component saturates
W_ABS, W_ANOM = 0.6, 0.4


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _phi(z: float) -> float:
    """Standard-normal CDF (same as drought_climatology's, kept local to avoid a cross-import)."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def heat_anomaly_score(z: float) -> float:
    """0–100 heat-hazard score from a STANDARDIZED grain-fill temperature anomaly `z`
    (σ units, positive = hotter than normal). The exact mirror of `drought_score`'s
    Φ(−SPEI)×100: here Φ(+z)×100, so a season one σ hotter than normal reads ~84, two σ
    ~98. This is the crop-FIT driver score for heat (the anomaly-percentile analogue of the
    SPEI drought score), deliberately distinct from the cell-scoring `heat_score` above,
    which also carries an absolute-stress term and forward warming."""
    if z is None:
        return 0.0
    return round(max(0.0, min(100.0, 100.0 * _phi(z))), 1)


def heat_score(temp_c: float, clim_mean: float, clim_std: float,
               scenario: str = "baseline", horizon: str = "current",
               lat: float | None = None) -> float:
    """0–100 heat-hazard score for a cell (absolute stress + anomaly), with forward warming.
    `lat` (if known) applies AR6 land/latitude amplification to the warming shift."""
    if clim_std is None or clim_std <= 0:
        return 0.0
    warming = warming_delta(scenario, horizon, lat)
    t = temp_c + warming
    abs_stress = _clip01((t - T_COMFORT) / (T_SEVERE - T_COMFORT))
    anom = _clip01((t - clim_mean) / clim_std / Z_FULL)
    return round(100.0 * _clip01(W_ABS * abs_stress + W_ANOM * anom), 1)
