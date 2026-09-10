"""Severe-convective-storm (tornado / large hail / damaging wind) potential — an environment-based screening.

Tornadoes have no global hazard map (national catalogues are regional and biased by population). The physically
grounded, GLOBAL way to represent the peril is the convective-storm ENVIRONMENT: the climatological co-presence
of instability (CAPE) and deep-layer wind shear (0–6 km), the accepted proxy for severe-convective potential
(Taszarek et al. 2021, ERA5). This is WIRED-READY: the scorer reads a precomputed global climatology field
data/convective/convective_potential.npz (a 0–100 potential on a lat/lon grid, built on infrastructure from
ERA5 CAPE × shear via scripts/build_convective_potential.py — ERA5 needs a Copernicus CDS key and is large),
and returns 'insufficient_data' until that field is built. Screening-tier, disclosed as an environment index,
never a tornado-frequency figure. This one channel also covers large hail and damaging convective wind.
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

MODEL_VERSION = "severe-convective-spc-anchored-v2"
_ANCHOR = "data/convective/convective_anchor.json"
_NPZ = "data/convective/convective_potential.npz"


@lru_cache(maxsize=1)
def _anchor():
    """potential → annual probability of ≥1 damaging report (NOAA SPC, fitted 2000–2013, held out 2014–2023)."""
    if not os.path.exists(_ANCHOR):
        return None
    with open(_ANCHOR) as f:
        a = json.load(f)
    return a["mapping"]["potential"], a["mapping"]["annual_probability"], a["held_out"]


def damage_anchored_score(potential: float) -> Optional[float]:
    """score = 100 × annual probability that the ~600 km² cell sees a damaging severe-convective event."""
    a = _anchor()
    if a is None:
        return None
    import numpy as np
    return round(float(100.0 * np.interp(potential, a[0], a[1])), 2)


@lru_cache(maxsize=1)
def _field():
    if not os.path.exists(_NPZ):
        return None
    import numpy as np
    z = np.load(_NPZ)
    return {k: z[k] for k in z.files}   # expects lat, lon, potential (nlat×nlon, 0–100)


def _potential(lat: float, lon: float) -> Optional[float]:
    g = _field()
    if g is None:
        return None
    import numpy as np
    i = int(np.abs(g["lat"] - float(lat)).argmin())
    j = int(np.abs(g["lon"] - float(lon)).argmin())
    v = float(g["potential"][i, j])
    return None if v != v else max(0.0, min(100.0, v))


def score_severe_convective_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket, model_version FROM canonical_scores
            WHERE hazard_type='severe_convective' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex and ex["model_version"] == MODEL_VERSION:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    v = _potential(lat, lon)
    if v is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "Convective-potential data is not available for this location."}
    risk = damage_anchored_score(v)
    if risk is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "The damage anchor (data/convective/convective_anchor.json) is missing."}
    if ex:   # an older-version row is retired, never overwritten: the lane is append-only
        with get_session() as s:
            s.execute(text("""UPDATE canonical_scores SET valid_to = now() WHERE hazard_type='severe_convective' AND h3_cell=:c AND scenario=:sc
                              AND time_horizon=:h AND valid_to IS NULL AND model_version <> :mv"""), {"c": cell, "sc": scenario, "h": horizon, "mv": MODEL_VERSION})
    now = datetime.now(timezone.utc)
    shap = {"convective_potential": round(v, 2), "annual_probability_damaging_event": round(risk / 100.0, 3), "on_demand": True, "tier": "calibrated_frequency",
            "held_out": (_anchor() or (None, None, {}))[2],
            "method": "ERA5 CAPE × 0–6 km shear potential (Taszarek 2021) anchored to the annual probability of a damaging severe-convective report (NOAA SPC hail ≥1 in / severe wind / tornado; fitted 2000–2013, held out 2014–2023); CONUS fit transferred elsewhere through the same environment field"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'severe_convective', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
