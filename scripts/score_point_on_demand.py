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

Only seismic is wired here (Phase 1 scope) -- volcanic/storm on-demand catalog checks
and the gridded-hazard background-job path are later phases of this same plan.
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

MODEL_VERSION = "seismic-gmpe-ipe-v1"
INFLUENCE_KM = 400.0  # same radius as score_seismic_event.py — beyond this MMI is negligible


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
        """), {
            "score_id": str(uuid.uuid4()), "h3_cell": cell,
            "risk_score": round(risk, 2), "risk_bucket": score_to_bucket(risk).value,
            "mv": MODEL_VERSION, "vintage": best[0]["origin_time"], "shap": json.dumps(shap),
            "now": now,
        })

    return {"status": "scored", "h3_cell": cell,
            "risk_score": round(risk, 2), "risk_bucket": score_to_bucket(risk).value}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("lat", type=float)
    ap.add_argument("lon", type=float)
    a = ap.parse_args()
    print(score_seismic_point(a.lat, a.lon))
