"""
Score hazards for an ARBITRARY point on demand — the "any address on Earth" path.

Adapts scripts/score_seismic_event.py's physics exactly (same IPE, same "max over all
nearby events" rule) but around a QUERY POINT instead of "the latest mainshock", and
against the FULL seismic_events history (not a 14-day window) -- a background/baseline
hazard question ("how exposed is this address to earthquakes, historically") is a
different question from an active-sequence early-warning one, and needs the full
catalog to answer honestly. seismic_events now holds 10 years of global M>=5.0 USGS
data (scripts/ingest_usgs_seismic.py --days 3650 --min-mag 5.0), so most seismically
active places on Earth have real history to score against.

If NO event is on record within INFLUENCE_KM, this returns status='insufficient_data'
rather than fabricating a low number -- same governance rule as agriculture's "exposure
mapped, € pending" for unscored commodities. Absence of a recorded M>=5.0 event nearby
in our currently-ingested window is not the same claim as "this place has zero seismic
hazard."

Storm is the second hazard wired here, using the SAME "max over nearby events"
pattern: scripts/ingest_ibtracs_global.py ingests real global IBTrACS tracks (all
basins, last 10 years, tropical-storm-strength and up), and score_storm_point
finds the WORST wind speed this point would have felt from ANY nearby track
observation, via the EXISTING Modified Rankine Vortex physics
(ml/scoring/storm_physics.py) -- that physics already generalizes to any storm
without per-storm hand-curation, unlike volcanic's hazard zones.

Volcanic on-demand catalog checks are not built yet -- volcanic's hazard zones
(proximal/ashfall radii) are hand-curated per-volcano from published papers, with
no generic fallback formula decided yet, a genuinely different and harder problem
than storm's fully-physics-based generalization.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.seismic_physics import ipe_mmi, mmi_to_risk
from ml.scoring.storm_physics import track_point_score, default_rmax_km

MODEL_VERSION = "seismic-gmpe-ipe-v1"
STORM_MODEL_VERSION = "storm-rankine-vortex-ibtracs-v1"
INFLUENCE_KM = 400.0  # same radius as score_seismic_event.py — beyond this MMI is negligible
STORM_BBOX_DEG = 10.0  # ~1000km prefilter — generous, real tropical-cyclone wind fields extend far
STORM_MIN_SCORE = 15.0  # below this (~tropical-storm-force wind), treat as negligible, not "hazard felt"


def haversine(la1, lo1, la2, lo2):
    r = 6371.0
    p1, p2 = np.radians(la1), np.radians(la2)
    dp, dl = np.radians(la2 - la1), np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def score_seismic_point(lat: float, lon: float) -> dict:
    """Score seismic hazard at an arbitrary point, writing+caching into canonical_scores.

    Returns {"status": "scored", "risk_score": float, "risk_bucket": str, "h3_cell": str}
    or {"status": "insufficient_data", "h3_cell": str, "reason": str} if nothing's on record.
    """
    cell = h3.latlng_to_cell(lat, lon, 8)

    with get_session() as s:
        existing = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) risk_score, risk_bucket
            FROM canonical_scores
            WHERE hazard_type='seismic' AND h3_cell=:c AND scenario='baseline'
              AND time_horizon='current' AND valid_to IS NULL
        """), {"c": cell}).mappings().first()
        if existing:
            return {"status": "cached_hit", "h3_cell": cell,
                    "risk_score": existing["risk_score"], "risk_bucket": existing["risk_bucket"]}

        events = s.execute(text("""
            SELECT CAST(magnitude AS FLOAT) m, CAST(epicentre_lat AS FLOAT) lat,
                   CAST(epicentre_lon AS FLOAT) lon,
                   CAST(COALESCE(depth_km, 10) AS FLOAT) depth, origin_time
            FROM seismic_events
            WHERE epicentre_lat BETWEEN :lat_lo AND :lat_hi
              AND epicentre_lon BETWEEN :lon_lo AND :lon_hi
        """), {
            "lat_lo": lat - 5, "lat_hi": lat + 5,  # coarse bbox prefilter (~500km at most latitudes)
            "lon_lo": lon - 5, "lon_hi": lon + 5,
        }).mappings().all()

    nearby = [e for e in events if haversine(lat, lon, e["lat"], e["lon"]) <= INFLUENCE_KM]
    if not nearby:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": f"no M>=5.0 earthquake on record within {INFLUENCE_KM:.0f}km "
                          f"in our currently-ingested 2016-present catalog"}

    best_mmi, best = 0.0, None
    for e in nearby:
        d = haversine(lat, lon, e["lat"], e["lon"])
        mmi = float(ipe_mmi(e["m"], d, e["depth"]))
        if mmi > best_mmi:
            best_mmi, best = mmi, (e, d)
    risk = float(mmi_to_risk(best_mmi))
    now = datetime.now(timezone.utc)
    shap = {
        "mmi": round(best_mmi, 2), "driver_mag": best[0]["m"], "driver_dist_km": round(best[1], 1),
        "driver_time": str(best[0]["origin_time"]), "on_demand": True,
    }

    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores
                (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                 risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                 scored_at, valid_from, valid_to)
            VALUES
                (:score_id,:h3_cell,8,'seismic','baseline','current',
                 :risk_score,:risk_bucket,:mv,:vintage, CAST(:shap AS jsonb),
                 :now,:now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {
            "score_id": str(uuid.uuid4()), "h3_cell": cell,
            "risk_score": round(risk, 2), "risk_bucket": score_to_bucket(risk).value,
            "mv": MODEL_VERSION, "vintage": best[0]["origin_time"], "shap": json.dumps(shap),
            "now": now,
        })

    return {"status": "scored", "h3_cell": cell,
            "risk_score": round(risk, 2), "risk_bucket": score_to_bucket(risk).value}


def score_storm_point(lat: float, lon: float) -> dict:
    """Score tropical-cyclone hazard at an arbitrary point, writing+caching into
    canonical_scores. Same "max over nearby events" shape as score_seismic_point,
    but the "event" here is a single 6-hourly track OBSERVATION (a storm's
    lifetime is already naturally broken into these), and the physics is the
    Modified Rankine Vortex (ml/scoring/storm_physics.py) instead of an IPE.

    Returns {"status": "scored"/"cached_hit", "risk_score": float, "risk_bucket": str,
    "h3_cell": str} or {"status": "insufficient_data", "h3_cell": str, "reason": str}
    if no nearby track observation produces at least tropical-storm-force wind here.
    """
    cell = h3.latlng_to_cell(lat, lon, 8)

    with get_session() as s:
        existing = s.execute(text("""
            SELECT CAST(risk_score AS FLOAT) risk_score, risk_bucket
            FROM canonical_scores
            WHERE hazard_type='storm' AND h3_cell=:c AND scenario='baseline'
              AND time_horizon='current' AND valid_to IS NULL
        """), {"c": cell}).mappings().first()
        if existing:
            return {"status": "cached_hit", "h3_cell": cell,
                    "risk_score": existing["risk_score"], "risk_bucket": existing["risk_bucket"]}

        events = s.execute(text("""
            SELECT storm_id, storm_name, CAST(lat AS FLOAT) lat, CAST(lon AS FLOAT) lon,
                   CAST(max_wind_kt AS FLOAT) wind_kt, CAST(rmw_km AS FLOAT) rmw_km,
                   sshs_category, observation_time
            FROM storm_events
            WHERE lat BETWEEN :lat_lo AND :lat_hi AND lon BETWEEN :lon_lo AND :lon_hi
              AND max_wind_kt IS NOT NULL
        """), {
            "lat_lo": lat - STORM_BBOX_DEG, "lat_hi": lat + STORM_BBOX_DEG,
            "lon_lo": lon - STORM_BBOX_DEG, "lon_hi": lon + STORM_BBOX_DEG,
        }).mappings().all()

    best_score, best = 0.0, None
    for e in events:
        d = haversine(lat, lon, e["lat"], e["lon"])
        rmax = e["rmw_km"] if e["rmw_km"] else default_rmax_km(e["sshs_category"])
        score = float(track_point_score(d, e["wind_kt"], rmax))
        if score > best_score:
            best_score, best = score, (e, d, rmax)

    if best_score < STORM_MIN_SCORE:
        return {"status": "insufficient_data", "h3_cell": cell,
                "reason": "no tropical cyclone on record within range producing "
                          "at least tropical-storm-force wind here, in our currently-"
                          "ingested global 2016-present catalog (wind >=34kt storms only)"}

    now = datetime.now(timezone.utc)
    e, d, rmax = best
    shap = {
        "driver_storm": e["storm_name"], "driver_storm_id": e["storm_id"],
        "driver_wind_kt": e["wind_kt"], "driver_dist_km": round(d, 1),
        "driver_rmax_km": round(rmax, 1), "driver_time": str(e["observation_time"]),
        "on_demand": True,
    }

    with get_session() as s:
        s.execute(text("""
            INSERT INTO canonical_scores
                (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                 risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                 scored_at, valid_from, valid_to)
            VALUES
                (:score_id,:h3_cell,8,'storm','baseline','current',
                 :risk_score,:risk_bucket,:mv,:vintage, CAST(:shap AS jsonb),
                 :now,:now, NULL)
            ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane)
                WHERE valid_to IS NULL DO NOTHING
        """), {
            "score_id": str(uuid.uuid4()), "h3_cell": cell,
            "risk_score": round(best_score, 2), "risk_bucket": score_to_bucket(best_score).value,
            "mv": STORM_MODEL_VERSION, "vintage": e["observation_time"], "shap": json.dumps(shap),
            "now": now,
        })

    return {"status": "scored", "h3_cell": cell,
            "risk_score": round(best_score, 2), "risk_bucket": score_to_bucket(best_score).value}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    a = ap.parse_args()
    print(score_seismic_point(a.lat, a.lon))
