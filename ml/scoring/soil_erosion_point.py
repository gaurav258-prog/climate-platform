"""Soil-erosion hazard at an arbitrary point, fetch-free at runtime — reads the GloSEM global soil-erosion
raster directly.

A SCREENING-tier indicator of chronic soil loss by water erosion (RUSLE-based). The raster
(data/soil_erosion/GloSEM.tif, fetched by scripts/fetch_soil_erosion.py from ESDAC) is the Borrelli/Panagos
GloSEM soil-displacement field in t ha⁻¹ yr⁻¹ (~100 m, EPSG:4326). We sample the rate at (lat, lon) and map
it to 0–100 on a saturating scale anchored on the agronomic tolerance (~2 t ha⁻¹ yr⁻¹ ≈ low; ~10 ≈ 50; ~50 ≈
severe). Disclosed as screening (authoritative rate, not calibrated to a €). Returns 'insufficient_data' off
the raster (ocean, nodata, or the file not fetched — ESDAC is registration-gated) — never a fabricated 0.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

MODEL_VERSION = "soil-erosion-glosem-v1"
_RASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "soil_erosion" / "GloSEM.tif"
_EROSION_K = 14.4   # t ha⁻¹ yr⁻¹: ~2→13, ~10→50, ~50→97 (saturating)

_src = None


def _dataset():
    global _src
    if _src is None:
        if not _RASTER_PATH.exists():
            return None
        import rasterio
        _src = rasterio.open(_RASTER_PATH)
    return _src


def soil_loss_score(rate_t_ha_yr: float) -> float:
    return round(max(0.0, min(100.0, 100.0 * (1.0 - math.exp(-max(0.0, float(rate_t_ha_yr)) / _EROSION_K)))), 2)


def _rate(lat: float, lon: float) -> Optional[float]:
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


def score_soil_erosion_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Soil-erosion rate at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' off the raster or if not fetched."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='soil_erosion' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    rate = _rate(lat, lon)
    if rate is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no GloSEM soil-erosion coverage at this point (ocean / nodata / ESDAC raster not fetched)"}

    risk = soil_loss_score(rate)
    now = datetime.now(timezone.utc)
    shap = {"soil_loss_t_ha_yr": round(rate, 2), "on_demand": True, "tier": "screening",
            "method": "GloSEM (Borrelli/Panagos) soil displacement by water erosion, t ha⁻¹ yr⁻¹; authoritative rate, not calibrated to €"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'soil_erosion', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
