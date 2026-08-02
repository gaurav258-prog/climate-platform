"""Frost hazard at an arbitrary point, fetch-free — the frost analogue of water_stress_point.

Reads the global frost baseline (frost_baseline: the 1991–2020 coldest-night climatology per H3 cell ×
month, built by scripts/build_global_frost.py) exactly the way water_stress_point reads the soil-moisture
baseline. The annual frost hazard at a location is the coldest night of its coldest month, mapped to 0–100
by frost_climatology.frost_score (warming raises the night → less frost). Caches into canonical_scores;
returns 'insufficient_data' where the baseline has no coverage (open ocean, gaps) — never a fabricated 0.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.frost_climatology import frost_score

MODEL_VERSION = "frost-climatology-global-v1"
_BOX = 0.75  # degrees; the baseline grid is ~0.5°, so a small box always catches neighbouring cells


def _annual_coldest_night(lat: float, lon: float) -> float | None:
    """The coldest night of the year at the nearest baseline cell — MIN(coldest_night_c) over its months,
    picking the geographically nearest cell in a small lat/lon box (idx_frost_baseline_latlon)."""
    with get_session() as s:
        rows = s.execute(text("""
            SELECT lat, lon, MIN(coldest_night_c) AS coldest
            FROM   frost_baseline
            WHERE  lat BETWEEN :a AND :b AND lon BETWEEN :c AND :d
            GROUP  BY lat, lon
        """), {"a": lat - _BOX, "b": lat + _BOX, "c": lon - _BOX, "d": lon + _BOX}).mappings().all()
    if not rows:
        return None
    nearest = min(rows, key=lambda r: h3.great_circle_distance((lat, lon), (float(r["lat"]), float(r["lon"])), unit="km"))
    return float(nearest["coldest"])


def score_frost_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Frost hazard at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' where the baseline has no coverage."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='frost' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    coldest = _annual_coldest_night(lat, lon)
    if coldest is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no global frost baseline coverage near this point"}

    risk = frost_score(coldest, scenario, horizon, lat)
    now = datetime.now(timezone.utc)
    shap = {"annual_coldest_night_c": round(coldest, 2), "on_demand": True,
            "method": "coldest night of the coldest month vs coffee frost thresholds (4/−2°C) + parametric warming"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'frost', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
