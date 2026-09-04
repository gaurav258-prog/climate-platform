"""Solifluction hazard at an arbitrary point — a periglacial derived proxy (permafrost × gentle slope).

Solifluction (slow downslope flow of water-saturated soil over a frozen/impermeable layer) is a periglacial
process: it needs a freeze–thaw / permafrost setting AND a gentle-to-moderate slope (it occurs on shallow
angles, ~2–20°, unlike avalanche/landslide). No global solifluction dataset exists, so this DERIVES a screening
indicator from two layers we already hold: the Obu (2019) permafrost probability (ml/scoring/permafrost) and the
on-demand DEM slope (ml/scoring/terrain). Screening only — a periglacial-susceptibility flag, not a movement
model. Returns 'not_applicable' outside the permafrost domain or off the gentle-slope window; 'insufficient_data'
with no permafrost/DEM coverage.
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
from ml.scoring.permafrost_point import _probability as _permafrost_probability
from ml.scoring.terrain import slope_degrees

MODEL_VERSION = "solifluction-permafrost-slope-v1"
_SLOPE_PEAK = 9.0     # degrees — solifluction lobes favour gentle slopes
_SLOPE_SIG = 6.0


def _gentle_slope_factor(slope: float) -> float:
    """Gentle-slope window: ~0 on the flat (<1°) and on steep ground (>25°), peak near 9°."""
    if slope < 1.0:
        return 0.0
    return math.exp(-((slope - _SLOPE_PEAK) ** 2) / (2 * _SLOPE_SIG ** 2))


def solifluction_score(permafrost_prob: float, slope_deg: float) -> float:
    return round(100.0 * max(0.0, min(1.0, permafrost_prob)) * _gentle_slope_factor(slope_deg), 2)


def score_solifluction_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='solifluction' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    p = _permafrost_probability(lat, lon)
    if p is None:
        return {"status": "not_applicable", "h3_cell": cell, "risk_score": 0.0,
                "reason": "outside the permafrost/periglacial domain — no solifluction setting"}
    sl = slope_degrees(lat, lon)
    if sl is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no DEM coverage to derive slope at this point"}
    slope, _elev = sl
    risk = solifluction_score(p, slope)
    if risk < 1.0:
        return {"status": "not_applicable", "h3_cell": cell, "risk_score": 0.0,
                "reason": "no solifluction setting (permafrost probability low or slope outside the gentle window)"}
    now = datetime.now(timezone.utc)
    shap = {"permafrost_probability": round(p, 3), "slope_deg": round(slope, 1), "on_demand": True, "tier": "screening",
            "method": "Obu (2019) permafrost probability × gentle-slope window (~2–20°); derived periglacial susceptibility, not a movement model"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'solifluction', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
