"""Per-year hazard-score panels for a crop origin — the single builder shared by the fitter and the validator.

`fit_ranged_crop.py` (which ESTABLISHES a crop's published calibration) and the champion out-of-sample
validator (which records that same calibration's honest leave-one-out skill into the audit ledger) must build
the predictor identically, or the ledger would validate a different model than the one that publishes. So the
three per-year score builders live here, once, and both callers import them.

Each builder returns {year: 0–100 hazard score} for one region×driver×season, read from the ERA5 baselines on
disk (data/era5_baseline/{region}_1991_2024_monthly.nc, plus the soil-moisture file for the soil_water driver).
"""
from __future__ import annotations

import math

from ml.features import soil_moisture as smf
from ml.features.drought import baseline_nc, compute_indices, load_monthly, seasonal_by_year
from ml.scoring.drought_climatology import drought_score
from ml.scoring.heat_climatology import heat_anomaly_score
from ml.scoring.soil_water_climatology import soil_water_score


def drought_scores(region: str, scale: int, months: list[int]) -> dict[int, float]:
    ds = load_monthly(baseline_nc(region))
    seasonal = seasonal_by_year(compute_indices(ds, scale=scale), months)
    return {r["year"]: drought_score(r["spei"]) for r in seasonal if r.get("spei") is not None}


def heat_scores(region: str, months: list[int]) -> dict[int, float]:
    """Per-year grain-fill HEAT score from the seasonal temperature anomaly. Standardize each year's season-mean
    temp anomaly (already vs the 1991–2020 monthly normal) by the interannual σ of that seasonal anomaly, then
    map Φ(z)×100 — so a season one σ hotter than normal reads ~84. The right driver for crops killed by heat
    during flowering (US Corn Belt maize), where SPEI-drought explains ~nothing."""
    ds = load_monthly(baseline_nc(region))
    seasonal = seasonal_by_year(compute_indices(ds), months)
    anoms = {r["year"]: r["temp_anom_c"] for r in seasonal
             if r.get("temp_anom_c") is not None and not math.isnan(r["temp_anom_c"])}
    if len(anoms) < 3:
        return {}
    vals = list(anoms.values())
    mean = sum(vals) / len(vals)
    sd = (sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5
    if sd <= 0:
        return {}
    return {y: heat_anomaly_score((a - mean) / sd) for y, a in anoms.items()}


def soil_water_scores(region: str, months: list[int]) -> dict[int, float]:
    """Per-year root-zone water-stress score from the soil-moisture anomaly — the better driver for dryland
    cereals (SPEI misses the deep antecedent soil water grain-fill draws on)."""
    smz = smf.anomaly(smf.load_root_zone(baseline_nc(region, 'soilmoisture')))
    return {r["year"]: soil_water_score(r["sm_z"]) for r in smf.seasonal_by_year(smz, months)
            if r.get("sm_z") is not None}


def scores_for(region: str, driver: str, months: list[int], spei_scale: int = 6) -> dict[int, float]:
    """Dispatch to the right builder for `driver`. Returns {} for an unknown driver (caller treats as no panel)."""
    if driver == "drought":
        return drought_scores(region, spei_scale, months)
    if driver == "soil_water":
        return soil_water_scores(region, months)
    if driver == "heat":
        return heat_scores(region, months)
    return {}
