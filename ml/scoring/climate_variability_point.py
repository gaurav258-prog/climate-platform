"""Temperature- and precipitation-VARIABILITY hazards at an arbitrary point, fetch-free.

Two SCREENING-tier chronic indicators built from the same global monthly climatology (climatology_baseline,
1991–2020: per H3 cell × month temp_mean/std, precip_mean/std). Disclosed methodology, never backtested skill:

  • temperature variability — the annual SEASONAL AMPLITUDE (warmest-month minus coldest-month mean) plus the
    typical interannual spread, scored BASELINE-RELATIVE: mapped 0–100 through the empirical percentiles of
    seasonal amplitude across the land climatology, so "High" means elevated vs other land (top quartile) and
    "Very High" the top decile — a normal continental season is no longer automatically High.
  • precipitation / hydrological variability — the SEASONAL CONCENTRATION of rainfall (coefficient of variation
    of the monthly means: monsoonal / strongly-seasonal regimes read high, evenly-wet climates low) plus the
    interannual spread, damped where annual rainfall is negligible so a bone-dry desert isn't lifted by noise.

Both read the nearest baseline cell in a small lat/lon box and return 'insufficient_data' off-coverage.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

TEMP_VAR_VERSION = "temp-variability-climatology-v2-baseline-relative"
PRECIP_VAR_VERSION = "precip-variability-climatology-v1"
_BOX = 0.75

# Baseline-relative anchoring (disclosed). "High"/"Very High" mean the seasonal temperature amplitude is
# ELEVATED vs the LAND distribution of the 1991–2020 climatology — not merely large in absolute terms. The
# breakpoints are the empirical percentiles of seasonal amplitude (warmest- minus coldest-month mean) across the
# land cells (rng>2°C) of climatology_baseline: median land ≈11°C → mid-M, top quartile (≈24°C) enters High, top
# decile (≈30°C) enters Very High. So a normal continental season is no longer automatically "High" and the
# screen discriminates. Anchors are (seasonal_range_c, score); derived by scripts/calibrate_variability_anchors.py.
_TEMP_VAR_ANCHORS = [(0.0, 0.0), (3.4, 8.0), (4.9, 20.0), (11.0, 38.0), (24.4, 50.0),
                     (29.8, 74.0), (41.0, 88.0), (46.5, 95.0), (60.0, 100.0)]
_PRECIP_CV_K = 0.70      # cv 1.4→86, 0.7→63, 0.3→35 (precip variability reads 27% H/VH — already selective)


def _anchor(value: float, anchors: list) -> float:
    """Piecewise-linear map of a driver value through empirical (value, score) percentile anchors, clamped to
    the end scores outside the anchored range. Monotone non-decreasing in value."""
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if value <= x1:
            return y0 + (y1 - y0) * (value - x0) / (x1 - x0)
    return anchors[-1][1]


def temp_variability_score(seasonal_range_c: float, interannual_c: float = 0.0) -> float:
    base = _anchor(max(0.0, seasonal_range_c), _TEMP_VAR_ANCHORS)
    add = min(6.0, max(0.0, interannual_c) * 2.0)   # gentle interannual nudge (does not re-saturate the scale)
    return round(max(0.0, min(100.0, base + add)), 2)


def precip_variability_score(seasonal_cv: float, interannual_cv: float = 0.0,
                             annual_mean_mm_day: float = 1.0) -> float:
    base = 100.0 * (1.0 - math.exp(-max(0.0, seasonal_cv) / _PRECIP_CV_K))
    add = min(10.0, max(0.0, interannual_cv) * 10.0)
    damp = min(1.0, max(0.0, annual_mean_mm_day) / 0.5)   # negligible-rain deserts aren't lifted by noise
    return round(max(0.0, min(100.0, (base + add) * damp)), 2)


def _cell_months(lat: float, lon: float) -> Optional[list[dict]]:
    """The 12 monthly rows of the nearest baseline cell in a small box, or None off-coverage."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT lat, lon, month, CAST(temp_mean_k AS FLOAT) tm, CAST(temp_std_k AS FLOAT) ts,
                   CAST(precip_mean_mm AS FLOAT) pm, CAST(precip_std_mm AS FLOAT) ps
            FROM climatology_baseline
            WHERE lat BETWEEN :a AND :b AND lon BETWEEN :c AND :d
        """), {"a": lat - _BOX, "b": lat + _BOX, "c": lon - _BOX, "d": lon + _BOX}).mappings().all()
    if not rows:
        return None
    cells: dict = {}
    for r in rows:
        cells.setdefault((float(r["lat"]), float(r["lon"])), []).append(r)
    nearest = min(cells, key=lambda k: h3.great_circle_distance((lat, lon), k, unit="km"))
    return cells[nearest]


def _insert(cell: str, hazard: str, risk: float, mv: str, scenario: str, horizon: str, shap: dict) -> None:
    now = datetime.now(timezone.utc)
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, :hz, :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "hz": hazard, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": mv, "now": now, "shap": json.dumps(shap)})


def _cached(cell: str, hazard: str, scenario: str, horizon: str) -> Optional[dict]:
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type=:hz AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"hz": hazard, "c": cell, "sc": scenario, "h": horizon}).mappings().first()
    return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]} if ex else None


def score_temp_variability_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    hit = _cached(cell, "temp_variability", scenario, horizon)
    if hit:
        return hit
    months = _cell_months(lat, lon)
    if not months:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no climatology coverage near this point"}
    means = [m["tm"] for m in months]
    seasonal_range = max(means) - min(means)              # K == °C difference
    interannual = sum(m["ts"] for m in months) / len(months)
    risk = temp_variability_score(seasonal_range, interannual)
    _insert(cell, "temp_variability", risk, TEMP_VAR_VERSION, scenario, horizon,
            {"seasonal_range_c": round(seasonal_range, 2), "interannual_std_c": round(interannual, 2),
             "on_demand": True, "tier": "screening",
             "method": "annual seasonal temperature amplitude + interannual spread (1991–2020 climatology), "
                       "baseline-relative: percentile-anchored vs the land amplitude distribution (top quartile → "
                       "High, top decile → Very High)"})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}


def score_precip_variability_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    hit = _cached(cell, "precip_variability", scenario, horizon)
    if hit:
        return hit
    months = _cell_months(lat, lon)
    if not months:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no climatology coverage near this point"}
    pmeans = [m["pm"] for m in months]
    annual_mean = sum(pmeans) / len(pmeans)
    if annual_mean > 1e-6:
        var = sum((p - annual_mean) ** 2 for p in pmeans) / len(pmeans)
        seasonal_cv = math.sqrt(var) / annual_mean
    else:
        seasonal_cv = 0.0
    inter = [m["ps"] / m["pm"] for m in months if m["pm"] > 0.2]      # interannual CV over the wet months
    interannual_cv = (sum(inter) / len(inter)) if inter else 0.0
    risk = precip_variability_score(seasonal_cv, interannual_cv, annual_mean)
    _insert(cell, "precip_variability", risk, PRECIP_VAR_VERSION, scenario, horizon,
            {"seasonal_cv": round(seasonal_cv, 3), "interannual_cv": round(interannual_cv, 3),
             "annual_mean_mm_day": round(annual_mean, 3), "on_demand": True, "tier": "screening",
             "method": "seasonal concentration (CV of monthly means) + interannual spread, damped in near-zero-rain deserts"})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
