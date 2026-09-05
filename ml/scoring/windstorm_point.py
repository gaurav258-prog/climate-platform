"""Extratropical-windstorm hazard at an arbitrary point — the EU-Taxonomy 'Storm (blizzard, dust, sand)' peril.

DISTINCT from the tropical-cyclone channel (ml/scoring/storm_physics.py / H.STORM). Tropical-cyclone models
(IBTrACS Rankine vortex) do not represent extratropical windstorms — the dominant wind peril for European
(EBA) banks (Kyrill, Lothar, Xynthia) — nor blizzards / dust-&-sand storms. This reads the authoritative ERA5
instantaneous-10 m-wind-gust climatology (1991-2020 stormiest-month peak, data/wind/windstorm_gust_climatology.npz,
built by scripts/build_windstorm_climatology.py) and scores it BASELINE-RELATIVE: the gust field is a monthly
mean (not an instantaneous return level), so an absolute damage scale would floor everything — instead we
percentile-anchor against the climatology so 'High' = windier than ~75% of the globe and 'Very High' the top
decile, a discriminating relative-exposure screen. Climatological, so it does not vary by scenario/horizon
(carried flat into forward reports, like the other climatology channels). Screening tier until backtested.
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

MODEL_VERSION = "windstorm-era5-gust-climatology-v1"
_NPZ = "data/wind/windstorm_gust_climatology.npz"

# Baseline-relative anchors (gust m/s → 0-100), from the climatology's own percentiles (build script):
# p50 10.1 → mid-M, p75 12.6 → enter High, p90 14.7 → enter Very-High. Discriminating, disclosed.
_WIND_ANCHORS = [(0.0, 0.0), (6.9, 8.0), (8.2, 22.0), (10.1, 38.0), (12.6, 50.0),
                 (14.7, 74.0), (16.8, 92.0), (22.0, 100.0)]


def _anchor(v: float) -> float:
    if v <= _WIND_ANCHORS[0][0]:
        return _WIND_ANCHORS[0][1]
    if v >= _WIND_ANCHORS[-1][0]:
        return _WIND_ANCHORS[-1][1]
    for (x0, y0), (x1, y1) in zip(_WIND_ANCHORS, _WIND_ANCHORS[1:]):
        if v <= x1:
            return y0 + (y1 - y0) * (v - x0) / (x1 - x0)
    return _WIND_ANCHORS[-1][1]


@lru_cache(maxsize=1)
def _field():
    if not os.path.exists(_NPZ):
        return None
    import numpy as np
    z = np.load(_NPZ)
    return {k: z[k] for k in z.files}   # lat, lon, gust_ms (nlat×nlon)


def _gust(lat: float, lon: float) -> Optional[float]:
    g = _field()
    if g is None:
        return None
    import numpy as np
    i = int(np.abs(g["lat"] - float(lat)).argmin())
    j = int(np.abs(g["lon"] - float(lon)).argmin())
    v = float(g["gust_ms"][i, j])
    return None if v != v else v


def score_windstorm_point(lat: float, lon: float, scenario: str = "baseline", horizon: str = "current") -> dict:
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='windstorm' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    gust = _gust(lat, lon)
    if gust is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "windstorm gust climatology not built (ERA5 i10fg — infra + CDS key)"}
    risk = round(_anchor(gust), 2)
    now = datetime.now(timezone.utc)
    shap = {"gust_ms": round(gust, 2), "on_demand": True, "tier": "screening",
            "method": "ERA5 instantaneous-10m-wind-gust climatology (1991-2020 stormiest-month), baseline-relative "
                      "percentile-anchored vs the global climatology (top quartile → High, top decile → Very High); "
                      "extratropical windstorm / blizzard / dust-sand storm — distinct from tropical cyclone"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to)
            VALUES (:id, :c, 8, 'windstorm', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": risk,
               "b": score_to_bucket(risk).value, "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": risk, "risk_bucket": score_to_bucket(risk).value}
