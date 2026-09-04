"""Soil-degradation hazard at an arbitrary point, fetch-free at runtime — reads a global land-degradation raster.

A SCREENING-tier indicator of chronic land/soil degradation. The authoritative global layers are ISRIC GLADA
(GLADIS) land-degradation (NDVI-trend based) and FAO's degradation assessments; there is no single clean
anonymous GeoTIFF, so this is WIRED-READY — the scorer samples data/soil_degradation/degradation.tif (a 0–100
or classed degradation index, WGS84) exactly like landslide/subsidence, and returns 'insufficient_data' until
that raster is dropped in by scripts/fetch_soil_degradation.py. No fabricated score is ever returned.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

MODEL_VERSION = "soil-degradation-glada-v1"
_RASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "soil_degradation" / "degradation.tif"
_src = None


def _dataset():
    global _src
    if _src is None:
        if not _RASTER_PATH.exists():
            return None
        import rasterio
        _src = rasterio.open(_RASTER_PATH)
    return _src


def _index(lat: float, lon: float) -> Optional[float]:
    src = _dataset()
    if src is None:
        return None
    b = src.bounds
    if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
        return None
    val = float(next(src.sample([(lon, lat)]))[0])
    nod = src.nodata
    if (nod is not None and val == nod) or val != val or val < 0.0:
        return None
    return val


def score_soil_degradation_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='soil_degradation' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    v = _index(lat, lon)
    if v is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no land-degradation coverage at this point (ocean / nodata / GLADA raster not fetched)"}
    risk = round(max(0.0, min(100.0, v)), 2)
    now = datetime.now(timezone.utc)
    shap = {"degradation_index": round(v, 2), "on_demand": True, "tier": "screening",
            "method": "ISRIC GLADA / FAO land-degradation index (NDVI-trend based); authoritative index, not calibrated to €"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'soil_degradation', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
