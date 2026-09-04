"""Saline-intrusion hazard at an arbitrary point — a coastal screening proxy built from the sea-level machinery.

Saltwater intrusion into coastal aquifers is driven by (a) how LOW and (b) how CLOSE to the coast the land is,
amplified by sea-level rise pushing the salt wedge inland. There is no clean global coastal-aquifer-salinity
raster, so this is an HONEST PROXY — the low-elevation-coastal-zone (LECZ) susceptibility × an SLR amplifier —
disclosed as a screening indicator, NOT a hydrogeological model of a specific aquifer. It reuses exactly the
inputs the coastal-flood channel already fetches on demand (elevation via Copernicus GLO-90 DEM + distance to
the Natural Earth coastline), so it needs no new data.

  • inland (> COAST_KM from the coast) → 'not_applicable' (never a fabricated 0)
  • susceptibility = proximity(dist) × lowland(elevation), 0–1, then amplified by the AR6 SLR at scenario ×
    horizon (baseline/current = today's susceptibility, no amplification).
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.coastal_flood_point import _ensure_coastal_exposure
from ml.scoring.sea_level import COAST_KM, slr_projection

MODEL_VERSION = "saline-intrusion-lecz-slr-v1"
_PROX_KM = 8.0     # proximity decay: <1 km ~1.0, ~8 km ~0.37 (intrusion is strongly coast-proximate)
_ELEV_M = 12.0     # lowland decay: 0–2 m ~1.0, ~12 m ~0.37 (aquifer vulnerability falls with elevation)
_SLR_AMP = 0.6     # each metre of SLR amplifies susceptibility by up to 60%


def saline_susceptibility(elevation_m: float, dist_km: float) -> float:
    """0–1 low-elevation-coastal-zone susceptibility (both close AND low needed)."""
    prox = math.exp(-max(0.0, dist_km) / _PROX_KM)
    low = math.exp(-max(0.0, elevation_m) / _ELEV_M)
    return prox * low


def score_saline_intrusion_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    """Coastal saline-intrusion susceptibility at (lat, lon); caches into canonical_scores. Returns
    {status, risk_score, risk_bucket, h3_cell} — 'not_applicable' inland, 'insufficient_data' with no elevation."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='saline_intrusion' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    elev, dist, is_coastal, _subs = _ensure_coastal_exposure(cell, lat, lon)
    if elev is None:
        return {"status": "insufficient_data", "h3_cell": cell, "reason": "no elevation available for this point"}
    if not is_coastal:
        return {"status": "not_applicable", "h3_cell": cell, "risk_score": 0.0,
                "reason": f"more than {COAST_KM:.0f} km from the coast — no coastal-aquifer intrusion pathway"}

    base = saline_susceptibility(elev, dist)
    slr = slr_projection(scenario, horizon)
    slr_m = slr.median_m if slr is not None else 0.0
    risk = round(min(100.0, 100.0 * base * (1.0 + _SLR_AMP * max(0.0, slr_m))), 2)

    now = datetime.now(timezone.utc)
    shap = {"elevation_m": elev, "dist_to_coast_km": round(dist, 2), "slr_m": round(slr_m, 3),
            "on_demand": True, "tier": "screening",
            "method": "low-elevation-coastal-zone susceptibility (proximity × lowland) × AR6 SLR amplifier; screening proxy, not a hydrogeological aquifer model"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'saline_intrusion', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
