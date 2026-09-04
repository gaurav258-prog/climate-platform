"""On-demand chronic water-stress scoring for an arbitrary point, from the global soil-moisture baseline.

Chronic root-zone aridity: how dry is this cell's 1991-2020 baseline root-zone soil water, scored
BASELINE-RELATIVE against the land soil-moisture distribution (driest quartile → High, driest decile → Very
High), so a normally-moist cell is not automatically flagged. Warming dries the root zone (more
evapotranspiration, less snowpack carryover),
so forward horizons raise the score by a parametric per-°C term — the same parametric-warming approach
heat/drought use for projections. It is a pure function of the already-built GLOBAL soil_moisture_baseline
(no live fetch), so it scores anywhere synchronously — the counterpart to heat_chronic_point for water.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.heat_climatology import HORIZON_FRACTION, SCENARIO_WARMING_C

MODEL_VERSION = "soil-water-aridity-global-v2-baseline-relative"
BOX = 0.7
DRY_PER_C = 4.0               # extra chronic-stress score points per °C warming (parametric v0)

# Baseline-relative anchoring (disclosed). Chronic water stress is scored against the LAND distribution of
# 1991–2020 root-zone soil moisture, not an absolute wet/dry pair — so "High" means DRIER than most land (driest
# quartile), "Very High" the driest decile, and a normally-moist cell is no longer automatically High. Anchors
# are (sm_mean m3/m3, score), monotonically decreasing in moisture; land percentiles (sm>0.02): driest-decile
# p10≈0.123 → 75, driest-quartile p25≈0.182 → 50, median p50≈0.242 → 38, wet p75≈0.332 → 20, p90≈0.390 → 8.
_SM_ANCHORS = [(0.06, 100.0), (0.123, 75.0), (0.182, 50.0), (0.242, 38.0), (0.332, 20.0), (0.390, 8.0), (0.45, 0.0)]


def _sm_anchor(sm: float) -> float:
    """Piecewise-linear map of baseline soil moisture through the land-distribution percentile anchors, clamped."""
    if sm <= _SM_ANCHORS[0][0]:
        return _SM_ANCHORS[0][1]
    if sm >= _SM_ANCHORS[-1][0]:
        return _SM_ANCHORS[-1][1]
    for (x0, y0), (x1, y1) in zip(_SM_ANCHORS, _SM_ANCHORS[1:]):
        if sm <= x1:
            return y0 + (y1 - y0) * (sm - x0) / (x1 - x0)
    return _SM_ANCHORS[-1][1]


def _sm_mean(lat: float, lon: float) -> float | None:
    with get_session() as s:
        rows = s.execute(text("""
            SELECT lat, lon, avg(sm_mean) AS sm FROM soil_moisture_baseline
            WHERE lat BETWEEN :a AND :b AND lon BETWEEN :c AND :d
            GROUP BY lat, lon
        """), {"a": lat - BOX, "b": lat + BOX, "c": lon - BOX, "d": lon + BOX}).mappings().all()
    if not rows:
        return None
    nearest = min(rows, key=lambda r: h3.great_circle_distance((lat, lon), (float(r["lat"]), float(r["lon"])), unit="km"))
    return float(nearest["sm"])


def score_water_stress_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Chronic root-zone water-stress at an arbitrary point; caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' where the baseline has no coverage."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='soil_water' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}
    sm = _sm_mean(lat, lon)
    if sm is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no global soil-moisture baseline coverage near this point"}
    base = _sm_anchor(sm)
    warming = SCENARIO_WARMING_C.get(scenario, 0.6) * HORIZON_FRACTION.get(horizon, 0.0)
    risk = round(max(0.0, min(100.0, base + warming * DRY_PER_C)), 1)
    now = datetime.now(timezone.utc)
    shap = {"sm_mean": round(sm, 3), "warming_c": round(warming, 2), "on_demand": True,
            "method": "chronic root-zone aridity, baseline-relative: percentile-anchored vs the land soil-moisture "
                      "distribution (driest quartile → High, driest decile → Very High) + parametric warming drying"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'soil_water', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
