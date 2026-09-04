"""Avalanche hazard at an arbitrary point — an honest terrain × cold-climate screening proxy.

There is no global avalanche-hazard map (national avalanche services are mountain-regional). This is a
disclosed SCREENING PROXY combining the two necessary conditions: a release-angle SLOPE (avalanches release
mostly on 30–45° slopes) AND a snow-bearing cold climate (high elevation or high latitude). Slope comes from
the on-demand DEM stencil (ml/scoring/terrain); the snow-climate factor is a coarse elevation/latitude proxy.
Screening only — it flags terrain PREDISPOSITION, not a snowpack-stability forecast. Returns 'not_applicable'
where there is effectively no avalanche terrain (flat or snow-free), 'insufficient_data' with no DEM coverage.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.terrain import slope_degrees

MODEL_VERSION = "avalanche-terrain-snow-proxy-v1"
_SLOPE_PEAK = 38.0    # degrees — centre of the avalanche release window
_SLOPE_SIG = 12.0


def _slope_factor(slope: float) -> float:
    """Release-angle window: ~0 below 20° / above ~60°, peak near 38°."""
    return math.exp(-((slope - _SLOPE_PEAK) ** 2) / (2 * _SLOPE_SIG ** 2))


def _snow_factor(elevation_m: float, lat: float) -> float:
    """Coarse snow-bearing-climate proxy from elevation and latitude, 0–1."""
    by_elev = (elevation_m - 500.0) / 2500.0     # 500 m → 0, 3000 m → 1
    by_lat = (abs(lat) - 45.0) / 20.0            # 45° → 0, 65° → 1
    return max(0.0, min(1.0, max(by_elev, by_lat)))


def avalanche_score(slope_deg: float, elevation_m: float, lat: float) -> float:
    return round(100.0 * _slope_factor(slope_deg) * _snow_factor(elevation_m, lat), 2)


def score_avalanche_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='avalanche' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    sl = slope_degrees(lat, lon)
    if sl is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no DEM coverage to derive slope at this point"}
    slope, elev = sl
    risk = avalanche_score(slope, elev, lat)
    if risk < 1.0:
        return {"status": "not_applicable", "h3_cell": cell, "risk_score": 0.0,
                "reason": "no avalanche terrain here (too flat / no snow-bearing climate)"}
    now = datetime.now(timezone.utc)
    shap = {"slope_deg": round(slope, 1), "elevation_m": round(elev, 0), "on_demand": True, "tier": "screening",
            "method": "terrain release-angle window (~30–45°) × elevation/latitude snow-climate proxy; screening predisposition, not a snowpack-stability forecast"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'avalanche', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
