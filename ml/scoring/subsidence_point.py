"""Land-subsidence hazard at an arbitrary point, fetch-free at runtime — reads the Global Subsidence
Susceptibility raster directly.

A SCREENING-tier indicator of terrain/hydrogeological PREDISPOSITION to land subsidence (aquifer-system
compaction, lithology, groundwater depletion, urban load — Herrera-García et al. 2021, Science), not an
InSAR-measured settlement nowcast. The raster (data/subsidence/GSS.tif, fetched by scripts/fetch_subsidence.py)
is a ~1 km EPSG:4326 uint8 grid of susceptibility classes 1–6; we sample the pixel at (lat, lon) and map the
class to 0–100. Susceptibility is geophysical (predisposition), so it does not vary with the climate
scenario/horizon — the same honest posture as landslide/seismic. Returns 'insufficient_data' off the raster
(ocean, >90°N/<60°S, nodata, or the file not fetched) — never a fabricated 0.
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

MODEL_VERSION = "subsidence-herrera-gss-v1"
_RASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "subsidence" / "GSS.tif"
_NODATA = 15

# GSS six-level susceptibility class → 0–100 exposure. 1 very-low … 6 very-high (disclosed, discrete).
CLASS_SCORE = {1: 5.0, 2: 20.0, 3: 40.0, 4: 60.0, 5: 80.0, 6: 95.0}

_src = None  # lazily-opened rasterio dataset, reused across calls


def _dataset():
    global _src
    if _src is None:
        if not _RASTER_PATH.exists():
            return None
        import rasterio
        _src = rasterio.open(_RASTER_PATH)
    return _src


def _susceptibility_class(lat: float, lon: float) -> Optional[int]:
    src = _dataset()
    if src is None:
        return None
    b = src.bounds
    if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
        return None
    val = int(next(src.sample([(lon, lat)]))[0])
    if val < 1 or val > 6:   # 15 = nodata, 0 = unclassified
        return None
    return val


def score_subsidence_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Subsidence susceptibility at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' off the raster or if not fetched."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='subsidence' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    cls = _susceptibility_class(lat, lon)
    if cls is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no Global Subsidence Susceptibility coverage at this point (ocean / out of 60°S–90°N / nodata / not fetched)"}

    risk = CLASS_SCORE[cls]
    now = datetime.now(timezone.utc)
    shap = {"susceptibility_class": cls, "on_demand": True, "tier": "screening",
            "method": "Herrera-García et al. (2021) Global Subsidence Susceptibility class (aquifer-system/lithology/groundwater/urban load); geophysical predisposition, not an InSAR settlement nowcast"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'subsidence', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
