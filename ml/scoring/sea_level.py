"""Sea-level rise → coastal-flood hazard (a freeboard screening model with an honest band).

WHY. Most global financial/industrial hubs sit on or near a coast, so ignoring sea-level rise
under-counts the exposure that matters most. SLR is NOT a blanket % like the rainfall-driven flood
rule — it only threatens LOW-lying assets NEAR the coast, and its size depends on how much headroom
("freeboard") an asset has above the future extreme sea level.

INPUTS.
  • SLR projection — IPCC AR6 (WG1 Ch.9 / SPM) global-mean sea-level rise relative to 1995–2014,
    median with the *likely* (17–83%) range. The central estimate ALREADY includes thermal
    expansion + glacier + ice-sheet melt. A SEPARATE low-confidence high-end (rapid Antarctic
    ice-sheet collapse) is carried as a STRESS value, never folded into the headline.
    (v1 uses global-mean SLR; regional variation + local land subsidence are disclosed follow-ons.)
  • Elevation + distance-to-coast per cell (coastal_exposure table).

MODEL. exposure_level = today's extreme still-water above mean sea level (high tide + storm surge
allowance) + projected SLR. freeboard = elevation − exposure_level. Hazard rises smoothly as
freeboard → 0 and below; it is ZERO for inland cells (beyond COAST_KM) or well-elevated ones, and
NULL where elevation is unknown (never fabricated). This is a SCREENING model — it identifies which
assets sit in the coastal-inundation danger zone and how SLR worsens it — NOT a local hydrodynamic
surge model, and it models the HAZARD, not sea-wall defences (conservative; disclosed).
"""
from __future__ import annotations
import math
from typing import NamedTuple, Optional, Tuple

SEA_LEVEL_VERSION = "sea-level-ar6-v1"

# screening parameters (disclosed, not fitted)
COAST_KM = 25.0            # beyond this from the coast, no direct SLR/coastal-flood exposure
SURGE_ALLOWANCE_M = 2.0    # generic present-day extreme still-water above MSL (high tide + surge)
SCALE_M = 2.0             # freeboard transition scale of the hazard sigmoid


class SlrProjection(NamedTuple):
    median_m: float
    lo_m: float          # AR6 likely-range low (17%)
    hi_m: float          # AR6 likely-range high (83%)
    stress_m: float      # low-confidence high-end (ice-sheet collapse tail); STRESS only


# IPCC AR6 WG1 (2021) global-mean sea-level rise vs 1995–2014, metres — median (likely 17–83%).
# Scenario map: orderly_1_5c→SSP1-2.6, disorderly_2c→SSP2-4.5, hot_house_3_5c→SSP5-8.5.
# baseline & 'current' have no added SLR (today's sea level held) — consistent with the other
# forward hazards. stress_m = the low-confidence high-end for that scenario/horizon.
_AR6 = {
    ("orderly_1_5c", "2030"): SlrProjection(0.09, 0.08, 0.12, 0.15),
    ("orderly_1_5c", "2050"): SlrProjection(0.20, 0.17, 0.26, 0.34),
    ("orderly_1_5c", "2100"): SlrProjection(0.44, 0.32, 0.62, 0.88),
    ("disorderly_2c", "2030"): SlrProjection(0.09, 0.08, 0.12, 0.16),
    ("disorderly_2c", "2050"): SlrProjection(0.23, 0.20, 0.29, 0.40),
    ("disorderly_2c", "2100"): SlrProjection(0.56, 0.44, 0.76, 1.05),
    ("hot_house_3_5c", "2030"): SlrProjection(0.10, 0.09, 0.12, 0.18),
    ("hot_house_3_5c", "2050"): SlrProjection(0.25, 0.20, 0.30, 0.48),
    ("hot_house_3_5c", "2100"): SlrProjection(0.77, 0.63, 1.01, 1.88),
}


def slr_projection(scenario: str, horizon: str) -> Optional[SlrProjection]:
    """AR6 global-mean SLR for a scenario × horizon, or None where no SLR is applied (baseline/current)."""
    return _AR6.get((scenario, horizon))


def _score(elevation_m: float, slr_m: float) -> float:
    exposure_level = SURGE_ALLOWANCE_M + slr_m
    freeboard = elevation_m - exposure_level
    return 100.0 / (1.0 + math.exp(freeboard / SCALE_M))   # ~50 at freeboard 0, →100 below, →0 well above


def coastal_flood_score(elevation_m: Optional[float], dist_to_coast_km: Optional[float],
                        slr: Optional[SlrProjection]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(score, ci_lower, ci_upper) on 0–100. NULL where elevation is unknown or no SLR is applied;
    0 for inland cells (no coastal exposure); band from the AR6 likely SLR range."""
    if slr is None or elevation_m is None or dist_to_coast_km is None:
        return (None, None, None)
    if dist_to_coast_km > COAST_KM:
        return (0.0, None, None)                     # inland → definitively no SLR exposure (a real 0)
    central = round(_score(elevation_m, slr.median_m), 2)
    lo = round(_score(elevation_m, slr.lo_m), 2)     # less SLR → lower hazard
    hi = round(_score(elevation_m, slr.hi_m), 2)     # more SLR → higher hazard
    return (central, round(min(lo, hi), 2), round(max(lo, hi), 2))
