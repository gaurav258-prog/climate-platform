"""Soil / land-degradation hazard at an arbitrary point — the UNCCD SDG 15.3.1 degraded-land status.

Authoritative, open source — Trends.Earth SDG Indicator 15.3.1 global dataset (Conservation International;
Zenodo 10.5281/zenodo.17079487), the UNCCD "proportion of degraded land" indicator computed from ESA-CCI land
cover, land-productivity dynamics and SoilGrids soil-organic-carbon, per the SDG 15.3.1 Good Practice Guidance.
Band 1 is the headline status: -1 degraded / 0 stable / +1 improved.

The product is a 5.4 GB Cloud-Optimized GeoTIFF; rather than download it, we read the single pixel at the asset
on demand straight from the COG over HTTP (a range read of one tile — no bulk download), mapping the status to
0-100 (degraded → high). A locally-materialised raster at data/soil_degradation/degradation.tif (a 0-100 or
signed-status grid) OVERRIDES the remote read when present (infra path). Screening-tier; returns
'insufficient_data' off the land grid or if the source is unreachable — never a fabricated score.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

MODEL_VERSION = "soil-degradation-sdg1531-v1"
_LOCAL_PATH = Path(__file__).resolve().parents[2] / "data" / "soil_degradation" / "degradation.tif"
# Trends.Earth SDG 15.3.1 (Zenodo 17079487) COG, band 1 = 2000-2015 baseline degraded-land status.
_COG_URL = "/vsicurl/https://zenodo.org/records/17079487/files/TrendsEarth_SDG15.3.1_2000-2023.tiff"
_STATUS_BAND = 1

_src = None
_band = _STATUS_BAND
_is_local = False


def _dataset():
    global _src, _band, _is_local
    if _src is None:
        import rasterio
        if _LOCAL_PATH.exists():
            _src = rasterio.open(_LOCAL_PATH); _band = 1; _is_local = True
        else:
            os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
            os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "2")
            os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
            try:
                _src = rasterio.open(_COG_URL); _band = _STATUS_BAND; _is_local = False
            except Exception:
                return None
    return _src




def _sample(lat: float, lon: float) -> Optional[float]:
    src = _dataset()
    if src is None:
        return None
    b = src.bounds
    if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
        return None
    try:
        import numpy as np
        from rasterio.windows import Window
        row, col = src.index(lon, lat)
        a = src.read(_band, window=Window(col - 4, row - 4, 9, 9))   # ~2 km neighbourhood
    except Exception:
        return None
    flat = a.reshape(-1)
    if src.nodata is not None:
        flat = flat[flat != src.nodata]
    if flat.size == 0:
        return None
    if _is_local and float(flat.max()) > 1.5:
        # a locally-materialised raster is a 0–100 degradation index → mean over the neighbourhood
        return round(max(0.0, min(100.0, float(flat.mean()))), 2)
    # SDG 15.3.1 status (-1 degraded / 0 stable / +1 improved). The indicator IS the PROPORTION of degraded
    # land, so score = the degraded FRACTION of the neighbourhood × 100 — truthful (1% degraded → 1, not VH),
    # never "any degraded pixel flags the whole cell".
    return round(100.0 * float(np.mean(flat == -1)), 2)


def score_soil_degradation_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='soil_degradation' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    risk = _sample(lat, lon)
    if risk is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no SDG 15.3.1 land-degradation coverage at this point (ocean / nodata / source unreachable)"}
    risk = round(risk, 2)
    now = datetime.now(timezone.utc)
    shap = {"on_demand": True, "tier": "screening",
            "method": "UNCCD SDG 15.3.1 (Trends.Earth: ESA-CCI land cover + productivity + SoilGrids SOC); "
                      "score = proportion of degraded land (status -1) in the ~2 km neighbourhood × 100; screening, not calibrated to €"}
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
