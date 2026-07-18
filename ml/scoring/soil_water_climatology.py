"""Root-zone WATER-STRESS scoring — from the soil-moisture anomaly.

The soil-water counterpart to drought_climatology. Where drought scores meteorological deficit
(SPEI), this scores what is actually in the root zone: the standardized soil-moisture anomaly
(ml/features/soil_moisture). A drier-than-normal root zone is higher stress:

  soil_water_score(0–100) = Φ(−sm_z) × 100   (more negative anomaly = drier soil = higher)

Validated as the better driver for dryland CEREALS (Spanish durum wheat: soil moisture r²=0.445
vs SPEI 0.360 — the grain-fill draws on deep antecedent soil water a same-season rainfall index
misses). Warming dries soil (more evapotranspiration, less snowpack carryover), so forward
scenarios shift the anomaly DOWN by the same modest per-°C term drought uses — 2030/2050/2100
water stress rises.
"""
from __future__ import annotations

import math

from .heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

DRYING_PER_C = 0.12   # soil-moisture-z units of extra drying per °C warming (mirrors drought v0)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def soil_water_score(sm_z: float, scenario: str = "baseline", horizon: str = "current") -> float:
    """0–100 root-zone water-stress from the soil-moisture anomaly; warming drives it drier."""
    if sm_z is None:
        return 0.0
    drying = SCENARIO_WARMING_C.get(scenario, 0.0) * HORIZON_FRACTION.get(horizon, 0.0) * DRYING_PER_C
    return round(max(0.0, min(100.0, 100.0 * _phi(-(sm_z - drying)))), 1)
