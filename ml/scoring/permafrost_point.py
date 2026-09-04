"""Permafrost-thaw hazard at an arbitrary point, fetch-free at runtime — reads the global permafrost
probability raster directly.

A SCREENING-tier indicator of THAW EXPOSURE: assets sitting on high-probability permafrost face ground
degradation as it thaws. The raster (data/permafrost/PERPROB.tif, fetched by scripts/fetch_permafrost.py) is
the Obu et al. (2019) Permafrost Probability Fraction (0–1) at ~1 km in EPSG:3995 (Arctic Polar Stereographic),
covering the Northern Hemisphere ≥25°N. We transform (lat, lon) into the raster CRS, sample the probability,
and map it to 0–100. Presence of permafrost is a physical-state exposure, not a scenario response, so it is
disclosed as screening (not calibrated to a thaw-loss €). Returns 'insufficient_data' off the raster (outside
the NH permafrost domain, nodata, or the file not fetched) — never a fabricated 0.
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

MODEL_VERSION = "permafrost-obu-perprob-v1"
_RASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "permafrost" / "PERPROB.tif"

_src = None
_to_raster = None  # lazily-built WGS84 -> raster-CRS transformer


def _dataset():
    global _src, _to_raster
    if _src is None:
        if not _RASTER_PATH.exists():
            return None
        import rasterio
        from pyproj import Transformer
        _src = rasterio.open(_RASTER_PATH)
        _to_raster = Transformer.from_crs("EPSG:4326", _src.crs, always_xy=True)
    return _src


def _probability(lat: float, lon: float) -> Optional[float]:
    src = _dataset()
    if src is None:
        return None
    x, y = _to_raster.transform(lon, lat)   # -> raster CRS (metres, polar stereographic)
    b = src.bounds
    if not (b.left <= x <= b.right and b.bottom <= y <= b.top):
        return None
    val = float(next(src.sample([(x, y)]))[0])
    nod = src.nodata
    if nod is not None and val == nod:
        return None
    if val != val or val < 0.0:   # NaN or negative sentinel
        return None
    return max(0.0, min(1.0, val))


def score_permafrost_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Permafrost-probability thaw exposure at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' off the raster or if not fetched."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='permafrost' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    p = _probability(lat, lon)
    if p is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no permafrost-probability coverage at this point (outside NH ≥25°N permafrost domain / nodata / not fetched)"}

    risk = round(100.0 * p, 2)
    now = datetime.now(timezone.utc)
    shap = {"permafrost_probability": round(p, 3), "on_demand": True, "tier": "screening",
            "method": "Obu et al. (2019) permafrost probability fraction (TTOP model, 1 km); thaw-exposure state, not a scenario response"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'permafrost', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
