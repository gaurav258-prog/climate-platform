"""Glacial-lake outburst flood (GLOF) hazard at an arbitrary point — reads the preprocessed GIGLak exposure layer.

A SCREENING-tier indicator of exposure to a glacial-lake outburst: whether the asset sits within a size-scaled
buffer of a mapped glacial lake (GIGLak, 117k lakes), scored from the influencing lake's AREA (a proxy for
outburst volume) with distance decay. Disclosed as a PROXIMITY screen — it is not a hydraulic flow-routed
inundation model, so it over-includes cells that are near but not hydrologically downstream. Returns
'not_applicable' anywhere outside a glacial-lake buffer (the vast majority of the planet) — never a fabricated 0.
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

MODEL_VERSION = "glof-giglak-proximity-v1"
_LOOKUP_RES = 6


def glof_score(area_km2: float, dist_km: float) -> float:
    """Lake area (outburst-volume proxy) with distance decay → 0–100."""
    area_score = min(100.0, 35.0 + 30.0 * math.sqrt(max(0.0, area_km2)))
    decay = math.exp(-max(0.0, dist_km) / 12.0)
    return round(area_score * decay, 2)


def _lookup(cell6: str) -> Optional[dict]:
    with get_session() as s:
        r = s.execute(text("""
            SELECT CAST(lake_area_km2 AS FLOAT) a, CAST(lake_elev_m AS FLOAT) e, CAST(dist_km AS FLOAT) d
            FROM glacial_lake_cell WHERE h3_cell=:c
        """), {"c": cell6}).mappings().first()
    return dict(r) if r else None


def score_glacial_lake_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='glacial_lake_outburst' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    hit = _lookup(h3.cell_to_parent(cell, _LOOKUP_RES))
    if hit is None:
        return {"status": "not_applicable", "h3_cell": cell, "risk_score": 0.0,
                "reason": "not within the buffer of any mapped glacial lake — no GLOF exposure pathway"}

    risk = glof_score(hit["a"], hit["d"])
    now = datetime.now(timezone.utc)
    shap = {"lake_area_km2": round(hit["a"], 3), "lake_elevation_m": hit["e"], "dist_km": hit["d"],
            "on_demand": True, "tier": "screening",
            "method": "GIGLak glacial-lake inventory; area (outburst-volume proxy) × distance decay; proximity screen, not flow-routed"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'glacial_lake_outburst', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
