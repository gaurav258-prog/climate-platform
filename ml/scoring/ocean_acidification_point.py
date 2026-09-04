"""Ocean-acidification hazard at a coastal/marine point — reads the OceanSODA-ETHZ surface-pH climatology.

A SCREENING-tier MARINE layer: for a coastal or marine asset (aquaculture, fisheries, a financed seafood
operation), the recent surface-ocean pH at the nearest ocean cell, mapped so a LOWER pH (more acidified) →
higher score. It is deliberately inapplicable to inland land assets — a point that is not within reach of the
coast returns 'not_applicable' (never a fabricated 0), exactly as coastal erosion does inland. The pH field is
built to a compact grid by scripts/build_ocean_ph.py; until it exists the scorer returns 'insufficient_data'.

Reference frame: pre-industrial surface pH ≈ 8.2 (score 0) → ≈ 7.7 (score 100); today's global mean ≈ 8.05.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.coastal_flood_point import _ensure_coastal_exposure

MODEL_VERSION = "ocean-acidification-oceansoda-v1"
_NPZ = "data/ocean_ph/ocean_ph_grid.npz"
_PH_HIGH = 8.2     # reference (score 0)
_PH_LOW = 7.7      # strongly acidified (score 100)


@lru_cache(maxsize=1)
def _grid():
    if not os.path.exists(_NPZ):
        return None
    import numpy as np
    z = np.load(_NPZ)
    return {"lat": z["lat"], "lon": z["lon"], "ph": z["ph"]}


def ph_score(ph: float) -> float:
    return round(max(0.0, min(100.0, 100.0 * (_PH_HIGH - ph) / (_PH_HIGH - _PH_LOW))), 2)


def _nearest_ocean_ph(lat: float, lon: float) -> Optional[float]:
    g = _grid()
    if g is None:
        return None
    import numpy as np
    i = int(np.abs(g["lat"] - float(lat)).argmin())
    j = int(np.abs(g["lon"] - float(lon)).argmin())
    v = float(g["ph"][i, j])
    if v == v:                       # the sampled cell is ocean
        return v
    # nearest coastal cell may be land-NaN — search a small neighbourhood for the closest ocean cell
    ph = g["ph"]
    for r in range(1, 4):
        lo_i, hi_i = max(0, i - r), min(ph.shape[0], i + r + 1)
        lo_j, hi_j = max(0, j - r), min(ph.shape[1], j + r + 1)
        window = ph[lo_i:hi_i, lo_j:hi_j]
        finite = window[np.isfinite(window)]
        if finite.size:
            return float(finite.mean())
    return None


def score_ocean_acidification_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='ocean_acidification' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    if _grid() is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "ocean pH field not built (run scripts/build_ocean_ph.py on the OceanSODA product)"}
    _elev, _dist, is_coastal, _subs = _ensure_coastal_exposure(cell, lat, lon)
    if not is_coastal:
        return {"status": "not_applicable", "h3_cell": cell, "risk_score": 0.0,
                "reason": "inland land asset — ocean acidification applies to coastal/marine (aquaculture, fisheries) exposure only"}
    ph = _nearest_ocean_ph(lat, lon)
    if ph is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no surface-ocean pH near this point"}

    risk = ph_score(ph)
    now = datetime.now(timezone.utc)
    shap = {"surface_ph": round(ph, 3), "on_demand": True, "tier": "screening",
            "method": "OceanSODA-ETHZ recent surface-ocean pH; lower pH → higher score (ref 8.2→0, 7.7→100); marine/coastal screening"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'ocean_acidification', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
