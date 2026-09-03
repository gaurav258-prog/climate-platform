"""Changing-temperature and changing-precipitation hazards at an arbitrary point, from the CMIP6 field.

Two SCREENING-tier chronic indicators of the MAGNITUDE of projected climate change at a location, read from
the built global CMIP6 ensemble delta field (data/cmip6/cmip6_global_deltas.npz, via ml.scoring.cmip6).
Change is inherently forward-looking, so these are defined ONLY under a projection scenario × horizon —
under baseline/current there is no change and the scorers honestly return 'insufficient_data' (a "change"
hazard has no present-day value; pick a scenario/horizon). Disclosed methodology, ensemble-mean, never
backtested skill.

  • changing temperature — ensemble-mean warming (°C) vs the 1995–2014 baseline → 0–100 (saturating; +2 °C ≈ 50,
    +3.5 °C ≈ 70, +5 °C ≈ 85).
  • changing precipitation — |ensemble-mean fractional precip change| → 0–100 (both drying and wetting are
    hazards; ±25 % ≈ 50, ±50 % ≈ 75). None where the CMIP6 precip field is a gap (some desert/ocean cells).
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
from ml.scoring.cmip6 import cmip6_delta_latlon

CHG_TEMP_VERSION = "changing-temp-cmip6-v1"
CHG_PRECIP_VERSION = "changing-precip-cmip6-v1"
_TEMP_K = 2.9      # +2°C→50, +3.5°C→70, +5°C→85
_PRECIP_K = 0.36   # ±25%→50, ±50%→75


def changing_temp_score(dtas_c: float) -> float:
    return round(max(0.0, min(100.0, 100.0 * (1.0 - math.exp(-abs(float(dtas_c)) / _TEMP_K)))), 2)


def changing_precip_score(dpr_frac: float) -> float:
    return round(max(0.0, min(100.0, 100.0 * (1.0 - math.exp(-abs(float(dpr_frac)) / _PRECIP_K)))), 2)


def _cached(cell: str, hazard: str, scenario: str, horizon: str):
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type=:hz AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"hz": hazard, "c": cell, "sc": scenario, "h": horizon}).mappings().first()
    return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]} if ex else None


def _insert(cell, hazard, risk, mv, scenario, horizon, shap):
    now = datetime.now(timezone.utc)
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, :hz, :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "hz": hazard, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": mv, "now": now, "shap": json.dumps(shap)})


def score_changing_temp_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    hit = _cached(cell, "changing_temp", scenario, horizon)
    if hit:
        return hit
    d = cmip6_delta_latlon(lat, lon, scenario, horizon)
    if d is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "change is forward-looking — no CMIP6 delta at baseline/current (pick a projection scenario)"}
    risk = changing_temp_score(d.dtas_c)
    _insert(cell, "changing_temp", risk, CHG_TEMP_VERSION, scenario, horizon,
            {"warming_c": round(d.dtas_c, 2), "across_model_std_c": round(d.dtas_std_c, 2), "n_models": d.n_models,
             "on_demand": True, "tier": "screening", "method": "CMIP6 ensemble-mean warming vs 1995–2014"})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}


def score_changing_precip_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    hit = _cached(cell, "changing_precip", scenario, horizon)
    if hit:
        return hit
    d = cmip6_delta_latlon(lat, lon, scenario, horizon)
    if d is None or d.dpr_frac != d.dpr_frac:   # None, or NaN precip gap
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no CMIP6 precip delta here (baseline/current, or a desert/ocean field gap)"}
    risk = changing_precip_score(d.dpr_frac)
    _insert(cell, "changing_precip", risk, CHG_PRECIP_VERSION, scenario, horizon,
            {"precip_change_frac": round(d.dpr_frac, 3), "across_model_std": round(d.dpr_std, 3), "n_models": d.n_models,
             "on_demand": True, "tier": "screening", "method": "CMIP6 ensemble-mean |fractional precip change| vs 1995–2014"})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
