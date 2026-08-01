"""On-demand chronic water-stress scoring for an arbitrary point, from the global soil-moisture baseline.

Chronic root-zone aridity: how dry is this cell's 1991-2020 baseline root-zone soil water against a
physical wet/dry scale. Warming dries the root zone (more evapotranspiration, less snowpack carryover),
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
from ml.scoring.heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

MODEL_VERSION = "soil-water-aridity-global-v1"
BOX = 0.7
SM_DRY, SM_WET = 0.12, 0.40   # root-zone volumetric water (m3/m3): field-dry vs field-wet anchors
DRY_PER_C = 4.0               # extra chronic-stress score points per °C warming (parametric v0)


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
    base = max(0.0, min(1.0, (SM_WET - sm) / (SM_WET - SM_DRY))) * 100.0
    warming = SCENARIO_WARMING_C.get(scenario, 0.6) * HORIZON_FRACTION.get(horizon, 0.0)
    risk = round(max(0.0, min(100.0, base + warming * DRY_PER_C)), 1)
    now = datetime.now(timezone.utc)
    shap = {"sm_mean": round(sm, 3), "warming_c": round(warming, 2), "on_demand": True,
            "method": "chronic root-zone aridity vs 0.12–0.40 wet/dry anchors + parametric warming drying"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'soil_water', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
