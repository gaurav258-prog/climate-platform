"""
Drought hazard scoring — from SPEI (the validated coffee signal).

The coffee backtest showed 2021 was the driest year in 34 (SPEI −0.86), aligning with the
−12.7% production drop. SPEI is already a standardized anomaly (z), so the hazard score is
the drought percentile:

  drought_score(0–100) = Φ(−SPEI) × 100   (more negative SPEI = drier = higher)

Warming worsens drought (more evapotranspiration): forward scenarios shift SPEI DOWN by a
modest drying term (°C × DRYING_PER_C), so 2030/2050/2100 drought risk rises — the physical
opposite of frost. v0: gamma-fit SPEI + basin-specific drying sensitivity are the refinements.
"""
from __future__ import annotations

import math

from .heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

DRYING_PER_C = 0.12   # SPEI units of extra drought per °C warming (modest, v0)


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def drought_score(spei: float, scenario: str = "baseline", horizon: str = "current") -> float:
    """0–100 drought hazard from SPEI; warming drives it drier."""
    if spei is None:
        return 0.0
    drying = SCENARIO_WARMING_C.get(scenario, 0.0) * HORIZON_FRACTION.get(horizon, 0.0) * DRYING_PER_C
    return round(max(0.0, min(100.0, 100.0 * _phi(-(spei - drying)))), 1)
