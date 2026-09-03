"""Heavy-precipitation hazard at an arbitrary point, fetch-free — the extreme-rainfall analogue of
water_stress_point / frost_point.

Reads the global precipitation climatology (climatology_baseline: 1991–2020 monthly mean + std per H3 cell ×
month) exactly the way frost_point reads the frost baseline. For the nearest baseline cell it takes the
WETTEST month (max monthly mean precip) and that month's interannual std, maps them to 0–100 via
heavy_precip_climatology.heavy_precip_score (warming intensifies extreme rainfall ~7%/°C, Clausius–Clapeyron),
caches into canonical_scores, and returns 'insufficient_data' where the baseline has no coverage — never a
fabricated 0.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.heavy_precip_climatology import heavy_precip_score, warming_delta

MODEL_VERSION = "heavy-precip-climatology-global-v1"
_BOX = 0.75  # degrees; the baseline grid is ~0.5°, so a small box always catches neighbouring cells


def _wettest_month(lat: float, lon: float) -> dict | None:
    """The wettest month of the nearest baseline cell — its max monthly mean precip and that month's std,
    picking the geographically nearest cell in a small lat/lon box."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT lat, lon, month, CAST(precip_mean_mm AS FLOAT) AS pm, CAST(precip_std_mm AS FLOAT) AS ps
            FROM   climatology_baseline
            WHERE  lat BETWEEN :a AND :b AND lon BETWEEN :c AND :d
        """), {"a": lat - _BOX, "b": lat + _BOX, "c": lon - _BOX, "d": lon + _BOX}).mappings().all()
    if not rows:
        return None
    # nearest cell by great-circle distance, then its wettest month
    cells: dict[tuple, list] = {}
    for r in rows:
        cells.setdefault((float(r["lat"]), float(r["lon"])), []).append(r)
    nearest_key = min(cells, key=lambda k: h3.great_circle_distance((lat, lon), k, unit="km"))
    wettest = max(cells[nearest_key], key=lambda r: r["pm"])
    return {"precip_mm": float(wettest["pm"]), "std_mm": float(wettest["ps"] or 0.0), "month": int(wettest["month"])}


def score_heavy_precip_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Heavy-precipitation hazard at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' where the baseline has no coverage."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='heavy_precip' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    wet = _wettest_month(lat, lon)
    if wet is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no global precipitation-climatology coverage near this point"}

    risk = heavy_precip_score(wet["precip_mm"], wet["std_mm"], scenario, horizon)
    now = datetime.now(timezone.utc)
    shap = {"wettest_month": wet["month"], "wettest_month_precip_mm": round(wet["precip_mm"], 1),
            "wettest_month_std_mm": round(wet["std_mm"], 1), "warming_delta_c": warming_delta(scenario, horizon),
            "on_demand": True, "tier": "screening",
            "method": "wettest-month precip climatology (1991–2020) + variability, warmed ~7%/°C (Clausius–Clapeyron)"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'heavy_precip', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
