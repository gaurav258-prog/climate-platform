"""Heavy-precipitation (extreme-rainfall) exposure score from the precipitation climatology.

A SCREENING-tier indicator (not a calibrated event model): it maps a location's WETTEST-MONTH precipitation
climatology (1991–2020 monthly mean + interannual std, from climatology_baseline) to a 0–100 exposure score.
The reasoning is standard and disclosed, not fitted:

  • base intensity — a saturating curve on the wettest month's mean daily precipitation (mm/day, the unit of
    climatology_baseline.precip_mean_mm). Chosen against the real global distribution (median ~2, p99 ~12,
    max ~111 mm/day) so a monsoon month (~20 mm/day, e.g. Mumbai) reads ~71, a wet-temperate month (~2 mm/day,
    e.g. London) reads ~13, and an arid peak (~0.1 mm/day) reads ~1; saturates toward 100 for the wettest
    places on Earth (Cherrapunji ~35 mm/day ≈ 89). No hard cliffs.
  • variability bump — a high coefficient of variation (std/mean) on the wettest month means it swings a lot
    year-to-year, i.e. it is prone to extreme single events; adds up to +10, but SCALED BY the base intensity
    so a bone-dry cell with noisy near-zero values isn't spuriously lifted.
  • warming — extreme precipitation intensifies by ~7 % per °C of warming (the Clausius–Clapeyron relation,
    the same physical basis IPCC AR6 uses for extreme-rainfall scaling). Projections scale the wettest-month
    total by (1.07)^ΔT before mapping, ΔT taken from the parametric warming matrix below (disclosed, not CMIP6
    per-cell). This mirrors how the rest of the engine handles parametric projections (see frost_climatology).

Everything here is a stated methodology, published openly with the score — never presented as backtested skill.
"""
from __future__ import annotations

import math

# saturating-curve scale on WETTEST-MONTH mean daily precip (mm/day): score = 100·(1 − e^(−peak/K)).
# K=16 fits the real distribution: 2 mm/day ≈ 13, 20 mm/day ≈ 71, 35 mm/day ≈ 89, 111 mm/day → ~100.
K_MM = 16.0
CV_BUMP_MAX = 10.0        # variability (std/mean) adds at most this many points, scaled by base intensity
CC_PER_C = 0.07           # Clausius–Clapeyron: ~7% intensification of extreme precip per °C

# Parametric global-mean warming above the 1991–2020 baseline (°C), by NGFS scenario archetype × horizon.
# Disclosed methodology (not a CMIP6 per-cell delta) — consistent with the platform's parametric projections.
WARMING_DELTA_C: dict[str, dict[str, float]] = {
    "baseline":       {"current": 0.0, "2030": 0.9, "2050": 1.7, "2100": 2.7},
    "orderly_1_5c":   {"current": 0.0, "2030": 0.8, "2050": 1.3, "2100": 1.4},
    "disorderly_2c":  {"current": 0.0, "2030": 0.9, "2050": 1.8, "2100": 2.2},
    "hot_house_3_5c": {"current": 0.0, "2030": 1.0, "2050": 2.2, "2100": 3.5},
}


def warming_delta(scenario: str, horizon: str) -> float:
    return WARMING_DELTA_C.get(scenario, WARMING_DELTA_C["baseline"]).get(horizon, 0.0)


def heavy_precip_score(peak_month_precip_mm: float, peak_month_std_mm: float = 0.0,
                       scenario: str = "baseline", horizon: str = "current") -> float:
    """0–100 extreme-rainfall exposure at a location, from its wettest-month precipitation climatology.

    peak_month_precip_mm — mean monthly total of the wettest month (mm). peak_month_std_mm — that month's
    interannual std (mm). Warming intensifies the effective wettest-month total via Clausius–Clapeyron.
    """
    peak = max(0.0, float(peak_month_precip_mm))
    peak_eff = peak * (1.0 + CC_PER_C) ** warming_delta(scenario, horizon)
    base = 100.0 * (1.0 - math.exp(-peak_eff / K_MM))
    cv = (float(peak_month_std_mm) / peak) if peak > 1e-6 else 0.0
    bump = CV_BUMP_MAX * min(cv, 1.0) * (base / 100.0)   # variability matters only where there's real rainfall
    return round(max(0.0, min(100.0, base + bump)), 2)
