"""On-demand coastal-flood (sea-level-rise) scoring for an arbitrary point.

Closes the WS4d coverage gap: a newly-uploaded coastal asset in a cell not yet in `coastal_exposure`
now gets the SLR hazard in-request. For an unknown cell it fetches the two missing inputs — elevation
(Open-Meteo / Copernicus GLO-90 DEM, no key) and distance to the Natural Earth coastline (shapely,
cached) — upserts `coastal_exposure`, then scores. Inland cells return `not_coastal` (no fabricated
row); no coverage / no elevation returns `insufficient_data` (never a fake score). Append-only,
`ON CONFLICT DO NOTHING` so a race is a harmless no-op.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.sea_level import (coastal_flood_score, slr_projection, SlrProjection,
                                  SEA_LEVEL_VERSION, COAST_KM)

COASTLINE_CACHE = "data/coastline/ne_10m_coastline.geojson"   # fine coastline — resolves estuaries/deltas
COASTLINE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_coastline.geojson"
_ZERO = SlrProjection(0.0, 0.0, 0.0, 0.0)   # baseline / current: today's sea level, no band


@lru_cache(maxsize=1)
def _coastline():
    from shapely.geometry import shape
    from shapely.ops import unary_union
    if not os.path.exists(COASTLINE_CACHE):
        import urllib.request
        os.makedirs(os.path.dirname(COASTLINE_CACHE), exist_ok=True)
        with urllib.request.urlopen(COASTLINE_URL, timeout=30) as r:
            open(COASTLINE_CACHE, "wb").write(r.read())
    gj = json.load(open(COASTLINE_CACHE))
    return unary_union([shape(f["geometry"]) for f in gj["features"]])


def _elevation(lat: float, lon: float):
    import urllib.request
    try:
        url = f"https://api.open-meteo.com/v1/elevation?latitude={lat:.5f}&longitude={lon:.5f}"
        with urllib.request.urlopen(url, timeout=20) as r:
            el = json.load(r).get("elevation")
        return float(el[0]) if el else None
    except Exception:
        return None


def _ensure_coastal_exposure(cell: str, lat: float, lon: float):
    """Return (elevation_m, dist_to_coast_km, is_coastal), fetching + upserting if the cell is new."""
    with get_session() as s:
        row = s.execute(text("""
            SELECT elevation_m, dist_to_coast_km, is_coastal FROM coastal_exposure WHERE h3_cell=:c
        """), {"c": cell}).mappings().first()
    if row:
        return row["elevation_m"], row["dist_to_coast_km"], row["is_coastal"]
    from shapely.geometry import Point
    from shapely.ops import nearest_points
    elev = _elevation(lat, lon)
    # true great-circle distance to the NEAREST point on the coastline (correct at any latitude,
    # unlike a planar degree distance which overstates east-west distance toward the poles)
    near = nearest_points(_coastline(), Point(lon, lat))[0]
    dist = h3.great_circle_distance((lat, lon), (near.y, near.x), unit="km")
    is_coastal = dist <= COAST_KM
    now = datetime.now(timezone.utc)
    with get_session() as s:
        s.execute(text("""
            INSERT INTO coastal_exposure (h3_cell, latitude, longitude, elevation_m, dist_to_coast_km,
                is_coastal, source, fetched_at)
            VALUES (:c,:lat,:lon,:el,:d,:coastal,:src,:now)
            ON CONFLICT (h3_cell) DO UPDATE SET elevation_m=:el, dist_to_coast_km=:d, is_coastal=:coastal,
                source=:src, fetched_at=:now
        """), {"c": cell, "lat": lat, "lon": lon, "el": elev, "d": round(dist, 2), "coastal": is_coastal,
               "src": "Open-Meteo GLO-90 DEM + Natural Earth 110m coastline (on-demand)", "now": now})
    return elev, round(dist, 2), is_coastal


def score_coastal_flood_point(lat: float, lon: float, scenario: str = "baseline",
                              horizon: str = "current") -> dict:
    """Score sea-level-rise coastal flooding at an arbitrary point, caching into canonical_scores."""
    cell = h3.latlng_to_cell(lat, lon, 8)
    with get_session() as s:
        ex = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) rs, risk_bucket FROM canonical_scores
            WHERE hazard_type='coastal_flood' AND h3_cell=:c AND scenario=:sc AND time_horizon=:h AND valid_to IS NULL
        """), {"c": cell, "sc": scenario, "h": horizon}).mappings().first()
        if ex:
            return {"status": "cached_hit", "h3_cell": cell, "risk_score": ex["rs"], "risk_bucket": ex["risk_bucket"]}

    elev, dist, is_coastal = _ensure_coastal_exposure(cell, lat, lon)
    if elev is None:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no elevation available for this point"}
    if not is_coastal:
        return {"status": "not_coastal", "h3_cell": cell, "risk_score": 0.0,
                "reason": f"more than {COAST_KM:.0f} km from the coast — no sea-level exposure"}

    slr = slr_projection(scenario, horizon)
    if slr is None:                                  # baseline / current — today's exposure, no band
        sc, _, _ = coastal_flood_score(elev, dist, _ZERO); lo = hi = None
    else:
        sc, lo, hi = coastal_flood_score(elev, dist, slr)
    if sc is None:
        return {"status": "insufficient_data", "h3_cell": cell}
    now = datetime.now(timezone.utc)
    shap = {"elevation_m": elev, "dist_to_coast_km": dist, "on_demand": True,
            "method": "freeboard vs AR6 SLR (screen; hazard not defences)"}
    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores
                (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon, risk_score,
                 risk_bucket, score_ci_lower, score_ci_upper, model_version, data_vintage, shap_factors,
                 scored_at, valid_from, valid_to)
            VALUES (:id,:c,8,'coastal_flood',:sc,:h,:r,:b,:lo,:hi,:mv,:now,CAST(:shap AS jsonb),:now,:now,NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {"id": str(uuid.uuid4()), "c": cell, "sc": scenario, "h": horizon, "r": sc,
               "b": score_to_bucket(sc).value, "lo": lo, "hi": hi, "mv": SEA_LEVEL_VERSION,
               "now": now, "shap": json.dumps(shap)})
    return {"status": "scored", "h3_cell": cell, "risk_score": sc, "risk_bucket": score_to_bucket(sc).value}
