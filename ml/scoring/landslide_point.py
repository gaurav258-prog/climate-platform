"""Landslide hazard at an arbitrary point, fetch-free at runtime — reads NASA's Global Landslide
Susceptibility Map directly.

A SCREENING-tier indicator of terrain PREDISPOSITION to landslides (slope, geology, road networks, fault
zones, forest loss — NASA/LHASA, Stanley & Kirschbaum), not a rainfall-triggered event nowcast. The raster
(data/landslide/global_landslide_susceptibility.tif, fetched by scripts/fetch_landslide_susc.py) is a 30
arc-second (~1 km) int8 grid of susceptibility classes 0–5; we sample the pixel at (lat, lon) at full
resolution and map the class to 0–100. Susceptibility is geophysical (terrain), so it does not vary with the
climate scenario/horizon — the same honest posture as seismic/volcanic. Returns 'insufficient_data' off the
raster (ocean, >72°N/<60°S, or the file not fetched) — never a fabricated 0.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

MODEL_VERSION = "landslide-nasa-lhasa-susc-v1"
_RASTER_PATH = Path(__file__).resolve().parents[2] / "data" / "landslide" / "global_landslide_susceptibility.tif"
_NODATA = 127

# NASA susceptibility class → 0–100 exposure. 0 negligible … 5 very high (disclosed, discrete).
CLASS_SCORE = {0: 3.0, 1: 20.0, 2: 40.0, 3: 60.0, 4: 80.0, 5: 95.0}

def _susceptibility_class(lat: float, lon: float):
    """Read through the process-isolated raster sampler; None = outside the raster, nodata, or a read failure."""
    from services.geo.raster_sampler import info, sample
    meta = info(_RASTER_PATH)
    if meta is None:
        return None
    left, bottom, right, top = meta["bounds"]
    if not (left <= lon <= right and bottom <= lat <= top):
        return None
    got = sample(_RASTER_PATH, [(lon, lat)])
    if not got or not got[0]:
        return None
    val = int(got[0][0])
    nod = meta.get("nodata")
    if (nod is not None and val == nod) or val == _NODATA or val < 0 or val > 5:
        return None
    return val


def score_landslide_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Landslide susceptibility at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'insufficient_data' off the raster or if not fetched."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='landslide' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    cls = _susceptibility_class(lat, lon)
    if cls is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "No landslide-susceptibility coverage at this point (offshore, or outside the 60°S–72°N coverage area)."}

    risk = CLASS_SCORE[cls]
    now = datetime.now(timezone.utc)
    shap = {"susceptibility_class": cls, "on_demand": True, "tier": "screening",
            "method": "NASA LHASA global landslide-susceptibility class (slope/geology/roads/faults/forest-loss); geophysical predisposition, not a rainfall-triggered event forecast"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'landslide', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
