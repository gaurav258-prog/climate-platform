"""Wildfire hazard CLIMATOLOGY at any point — the standing wildfire lane (where fire is prone, year after year).

Replaces the day-of ERA5 fire-weather model as the SCORED wildfire lane. That model was judged on the official
EFFIS burnt-area record with every fire held out and had no skill (pooled AUC 0.44, scripts/backtest_wildfire_effis.py):
day-of weather cannot say WHERE a fire burns. Customers ask how fire-prone a location is, not whether it burns
today — a hazard climatology, the same shape as landslide (LHASA) and seismic. Three authoritative terms, all 0.25°:
  W  fire-WEATHER climatology — Copernicus CEMS/ECMWF Fire Weather Index (GEFF, ERA5-driven): mean annual days at
     EFFIS 'extreme' danger (FWI ≥ 38), 2006-2020            (scripts/build_fwi_climatology.py, EWDS)
  F  FUEL availability — fraction of burnable land per cell   (C3S ESA-CCI Fire burned-area product's own mask)
  H  observed burn HISTORY — mean annual burned fraction of burnable land, 2001-2019
                                                             (scripts/build_burned_area_climatology.py, CDS)
Disclosed, monotone, fixed-scale formulas (no fitted parameters):
  W = 100·(1 − exp(−days_extreme / 15))      15 extreme days/yr → 63, 45 → 95
  H = 100·(1 − exp(−burned_fraction / 0.02))  2 %/yr of the land burning → 63
  weather_fuel  : S = W · F                    (fully independent of any burn observation)
  with_history  : S = 0.6·W·F + 0.4·H          (H reuses the burn record → in-domain, disclosed)
Validation target is held out in TIME: EFFIS burn scars 2022-2024 (scripts/backtest_wildfire_climatology.py);
every input ends 2020. Geophysical-style standing layer: no scenario response (a warming shift of W is future
work), never a € on its own. Returns 'not_burnable' (score 0, a real answer) where F = 0 (ocean, ice, bare desert).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

import numpy as np

MODEL_VERSION = "wildfire-climatology-v1"
_DIR = Path(__file__).resolve().parents[2] / "data" / "wildfire"
FWI_PATH = _DIR / "fwi_climatology.npz"
BA_PATH = _DIR / "burned_area_climatology.npz"
W_SCALE_DAYS = 15.0
H_SCALE_FRAC = 0.02
HISTORY_WEIGHT = 0.4
VARIANTS = ("weather_fuel", "with_history")
PRODUCTION_VARIANT = "with_history"   # set by the backtest verdict (scripts/backtest_wildfire_climatology.py)

_grids: Optional[dict] = None


def load_grids() -> Optional[dict]:
    """Both climatologies on one 0.25° grid (BA cell centres; FWI is on 0.25° nodes → nearest-node lookup)."""
    global _grids
    if _grids is None and FWI_PATH.exists() and BA_PATH.exists():
        f, b = np.load(FWI_PATH), np.load(BA_PATH)
        _grids = {"fwi_lat": f["lat"], "fwi_lon": f["lon"], "days_extreme": f["days_extreme"],
                  "days_very_high": f["days_very_high"], "p95": f["p95"], "fwi_years": f["years"],
                  "ba_lat": b["lat"], "ba_lon": b["lon"], "burnable": b["burnable_fraction"],
                  "burned_frac": b["mean_annual_burned_fraction"], "ba_years": b["years"]}
    return _grids


def _idx(axis: np.ndarray, v: float) -> int:
    return int(np.abs(axis - v).argmin())


def _lon180(lon: float, axis: np.ndarray) -> float:
    return lon % 360.0 if axis.max() > 180.0 else ((lon + 180.0) % 360.0) - 180.0


def sample_terms(lat: float, lon: float, g: Optional[dict] = None) -> Optional[dict]:
    g = g or load_grids()
    if g is None:
        return None
    i, j = _idx(g["fwi_lat"], lat), _idx(g["fwi_lon"], _lon180(lon, g["fwi_lon"]))
    k, m = _idx(g["ba_lat"], lat), _idx(g["ba_lon"], _lon180(lon, g["ba_lon"]))
    return {"days_extreme": float(g["days_extreme"][i, j]), "days_very_high": float(g["days_very_high"][i, j]),
            "fwi_p95": float(g["p95"][i, j]), "burnable_fraction": float(g["burnable"][k, m]),
            "burned_fraction": float(np.nan_to_num(g["burned_frac"][k, m]))}


def wildfire_hazard(days_extreme: float, burnable_fraction: float, burned_fraction: float,
                    variant: str = "weather_fuel") -> dict:
    """Pure formula → {score, weather_term, fuel_term, history_term}. Vectorises over numpy arrays too."""
    w = 100.0 * (1.0 - np.exp(-np.maximum(days_extreme, 0.0) / W_SCALE_DAYS))
    f = np.clip(burnable_fraction, 0.0, 1.0)
    h = 100.0 * (1.0 - np.exp(-np.maximum(burned_fraction, 0.0) / H_SCALE_FRAC))
    if variant == "weather_fuel":
        s = w * f
    elif variant == "with_history":
        s = (1.0 - HISTORY_WEIGHT) * w * f + HISTORY_WEIGHT * h
    else:
        raise ValueError(f"unknown variant {variant!r}")
    return {"score": np.clip(s, 0.0, 100.0), "weather_term": w, "fuel_term": f, "history_term": h}


def score_point_pure(lat: float, lon: float, variant: str = "weather_fuel") -> Optional[dict]:
    t = sample_terms(lat, lon)
    if t is None:
        return None
    t = {k: (0.0 if math.isnan(v) else v) for k, v in t.items()}       # undefined (sea / no data) → no hazard, valid JSON
    r = wildfire_hazard(t["days_extreme"], t["burnable_fraction"], t["burned_fraction"], variant)
    out = {k: (round(float(v), 2) if not isinstance(v, str) else v) for k, v in r.items()}
    out.update({k: round(v, 4) for k, v in t.items()})
    out["variant"] = variant
    out["not_burnable"] = bool(t["burnable_fraction"] <= 0.0)
    return out


# ── DB-backed any-address scorer (standing lane) ────────────────────────────────────────────────────────────
def score_wildfire_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Standing wildfire hazard at (lat, lon), cached in canonical_scores (score_lane 'standing', this model
    version). A current wildfire row from an OLDER model in the standing lane (the retired day-of ERA5 model) is
    retired lane-scoped and replaced — append-only, same pattern as the batch engine. Returns
    {status, risk_score, risk_bucket, h3_cell}; 'insufficient_data' only when the climatologies are not built."""
    import json
    import uuid
    from datetime import datetime, timezone

    import h3
    from sqlalchemy import text

    from core.db.session import get_session
    from core.types import score_to_bucket
    from ml.scoring.engine import _retire_previous_scores

    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket, model_version FROM canonical_scores
            WHERE hazard_type='wildfire' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h
              AND score_lane='standing' AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
    if ex and ex["model_version"] == MODEL_VERSION:
        return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    r = score_point_pure(lat, lon, PRODUCTION_VARIANT)
    if r is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "wildfire climatologies not built (scripts/build_fwi_climatology.py, build_burned_area_climatology.py)"}
    risk = float(r["score"])
    now = datetime.now(timezone.utc)
    shap = {"on_demand": True, "tier": "screening", "model": MODEL_VERSION, "lane": "standing",
            "method": "fire-weather climatology (CEMS/ECMWF FWI extreme days 2006-2020) x burnable-land fraction "
                      + ("+ observed burn history (C3S ESA-CCI 2001-2019)" if PRODUCTION_VARIANT == "with_history" else
                         "(no burn observation used)") + "; disclosed fixed-scale formula, validated on EFFIS 2022-24 scars",
            **{k: v for k, v in r.items() if k != "score"}}
    with get_session() as s:
        if ex:
            _retire_previous_scores(s, [cell], "wildfire", scenario, now, score_lane="standing")
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to, score_lane)
            VALUES (:id, :c, 8, 'wildfire', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL, 'standing')
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
