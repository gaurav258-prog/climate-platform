"""
On-demand chronic-heat scoring for an arbitrary point.

Unlike every other gridded hazard here (flood/wildfire/pollution/heat_acute/
drought), chronic heat needs NO live external fetch — it's purely a function
of the 30-year climatology_baseline table already built (see
core/db/migrations/versions/b3c4d5e6f7a8_climatology_baseline.py). That means
it scores SYNCHRONOUSLY, in-request, the same cost tier as seismic
(scripts/score_point_on_demand.py) — no CDS queue wait, no background job,
no Celery task needed for this one.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.heat_chronic import heat_chronic_score

MODEL_VERSION = "heat-chronic-climatology-v1"
CLIMATOLOGY_BOX_DEG = 1.0  # same bounded-box nearest-neighbor convention as heat_point.py


def _monthly_climatology(lat: float, lon: float) -> dict[int, tuple[float, float]]:
    """All 12 months' (clim_mean_c, clim_std_c) for the nearest climatology_baseline
    grid point to (lat, lon) — one bounded-box query, not 12 separate ones."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT month, lat, lon, temp_mean_k, temp_std_k
            FROM climatology_baseline
            WHERE lat BETWEEN :lat_min AND :lat_max
              AND lon BETWEEN :lon_min AND :lon_max
        """), {
            "lat_min": lat - CLIMATOLOGY_BOX_DEG, "lat_max": lat + CLIMATOLOGY_BOX_DEG,
            "lon_min": lon - CLIMATOLOGY_BOX_DEG, "lon_max": lon + CLIMATOLOGY_BOX_DEG,
        }).mappings().all()
    if not rows:
        return {}

    # nearest grid point by (lat, lon) among the candidates -- pick its (lat, lon)
    # once, then only use rows AT that exact point (all 12 months share one location)
    nearest_latlon = min({(float(r["lat"]), float(r["lon"])) for r in rows},
                         key=lambda p: h3.great_circle_distance((lat, lon), p, unit="km"))
    return {
        int(r["month"]): (float(r["temp_mean_k"]) - 273.15, float(r["temp_std_k"]))
        for r in rows if (float(r["lat"]), float(r["lon"])) == nearest_latlon
    }


def score_heat_chronic_point(lat: float, lon: float, scenario: str = "baseline",
                              horizon: str = "current") -> dict:
    """Score chronic heat at an arbitrary point, writing+caching into canonical_scores.

    Returns {"status": "scored"/"cached_hit", "risk_score": float, "risk_bucket": str,
    "h3_cell": str} or {"status": "insufficient_data", ...} if the climatology
    baseline has no coverage near this point (open ocean, polar gaps)."""
    cell = h3.latlng_to_cell(lat, lon, 8)

    with get_session() as s:
        existing = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) risk_score, risk_bucket
            FROM canonical_scores
            WHERE hazard_type='heat_chronic' AND h3_cell=:c AND scenario=:sc
              AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if existing:
            return {"status": "cached_hit", "h3_cell": cell,
                    "risk_score": existing["risk_score"], "risk_bucket": existing["risk_bucket"]}

    monthly_clim = _monthly_climatology(lat, lon)
    if not monthly_clim or len(monthly_clim) < 12:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no global climatology baseline coverage near this point "
                          "(likely open ocean or a polar gap)"}

    result = heat_chronic_score(monthly_clim, scenario=scenario, horizon=horizon)
    risk = result["score"]
    now = datetime.now(timezone.utc)
    shap = {
        "expected_hot_days_per_year": result["expected_hot_days_per_year"],
        "hot_day_threshold_c": 30.0, "on_demand": True,
        "simplification": "mean-temp proxy for C3S's max-temp Hot Days indicator (conservative/lower-bound)",
    }

    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores
                (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                 risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                 scored_at, valid_from, valid_to)
            VALUES
                (:score_id, :h3_cell, 8, 'heat_chronic', :scenario, :horizon,
                 :risk_score, :risk_bucket, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
        """), {
            "score_id": str(uuid.uuid4()), "h3_cell": cell, "scenario": scenario, "horizon": horizon,
            "risk_score": risk, "risk_bucket": score_to_bucket(risk).value,
            "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap),
        })

    return {"status": "scored", "h3_cell": cell,
            "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
