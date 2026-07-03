"""
Score a tropical-cyclone track into canonical_scores using real physics.

Mirrors scripts/score_seismic_event.py's core idea exactly: a cell takes the MAX
hazard over all nearby "events" — for seismic that's an aftershock sequence, here
it's every 6-hourly track observation as the storm passes. The wind-decay physics
itself (ml/scoring/storm_physics.py) is a Modified Rankine Vortex, evaluated once
per (cell, track-point) pair.

Unlike volcanic's single fixed vent, a storm's track MOVES — so the H3 grid is
generated once around a fixed backtest region (Puerto Rico, from services/ingestion/
regions.py) rather than around one event's coordinates, and every track point within
range of that grid contributes its own decayed wind field; the cell keeps the max.

Usage:  python scripts/score_storm_event.py                      # Hurricane Maria (default)
        python scripts/score_storm_event.py --storm-id 2017260N12310
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone

import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.storm_physics import track_point_score, default_rmax_km
from services.ingestion.regions import get_region

MODEL_VERSION = "storm-rankine-vortex-ibtracs-v1"
REGION_KEY = "puerto_rico"
INFLUENCE_KM = 150.0          # beyond this a single track point's wind hazard is negligible
PREFILTER_KM = 500.0          # ignore track points far from the region entirely (perf)

_KM_PER_RING = h3.average_hexagon_edge_length(8, unit="km") * (3 ** 0.5) * 1.2
GRID_DISK_K = int(np.ceil(INFLUENCE_KM / _KM_PER_RING))


def haversine(la1, lo1, la2, lo2):
    r = 6371.0
    p1, p2 = np.radians(la1), np.radians(la2)
    dp, dl = np.radians(la2 - la1), np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def score_storm(storm_id: str):
    region = get_region(REGION_KEY)
    centre_lat = (region.min_lat + region.max_lat) / 2
    centre_lon = (region.min_lon + region.max_lon) / 2

    with get_session() as s:
        rows = s.execute(text("""
            SELECT observation_time, CAST(lat AS FLOAT) lat, CAST(lon AS FLOAT) lon,
                   CAST(max_wind_kt AS FLOAT) wind_kt, CAST(rmw_km AS FLOAT) rmw_km,
                   sshs_category, storm_name
            FROM storm_events WHERE storm_id = :sid ORDER BY observation_time
        """), {"sid": storm_id}).mappings().all()
    if not rows:
        print(f"  storm {storm_id}: no storm_events rows — run ingest_ibtracs_storm.py first")
        return 0

    name = rows[0]["storm_name"]
    # prefilter to track points that could plausibly matter for this region
    nearby = [r for r in rows if haversine(r["lat"], r["lon"], centre_lat, centre_lon) <= PREFILTER_KM]
    if not nearby:
        print(f"  storm {storm_id} ({name}): track never comes within {PREFILTER_KM:.0f}km of {region.label}")
        return 0

    print(f"scoring {name} ({storm_id}) vs {region.label} — {len(nearby)}/{len(rows)} track points in range")

    centre = h3.latlng_to_cell(centre_lat, centre_lon, 8)
    cells = h3.grid_disk(centre, GRID_DISK_K)
    print(f"  scoring {len(cells)} H3 cells within ~{INFLUENCE_KM:.0f}km of the region centre …")

    now = datetime.now(timezone.utc)
    vintage = min(r["observation_time"] for r in nearby)

    records = []
    for cell in cells:
        clat, clon = h3.cell_to_latlng(cell)
        best_score, best = 0.0, None
        for r in nearby:
            d = float(haversine(clat, clon, r["lat"], r["lon"]))
            if r["wind_kt"] is None or d > INFLUENCE_KM:
                continue
            rmax = r["rmw_km"] if r["rmw_km"] else default_rmax_km(r["sshs_category"])
            sc = float(track_point_score(d, r["wind_kt"], rmax))
            if sc > best_score:
                best_score, best = sc, (r, d, rmax)
        if best is None:
            continue
        r, d, rmax = best
        shap = {
            "storm": name, "driver_time": str(r["observation_time"]), "driver_dist_km": round(d, 1),
            "driver_wind_kt": r["wind_kt"], "driver_sshs": r["sshs_category"],
            "rmax_km": round(rmax, 1), "rmax_source": "ibtracs_usa_rmw" if r["rmw_km"] else "category_fallback",
        }
        records.append({
            "score_id": str(uuid.uuid4()), "h3_cell": cell, "h3_resolution": 8,
            "hazard_type": "storm", "scenario": "baseline", "time_horizon": "current",
            "risk_score": round(best_score, 2), "risk_bucket": score_to_bucket(best_score).value,
            "model_version": MODEL_VERSION, "data_vintage": vintage,
            "scored_at": now, "valid_from": now, "shap": json.dumps(shap),
        })

    if not records:
        print("  no cells scored (track too far from every cell)"); return 0

    with get_session() as s:
        s.execute(text("""UPDATE canonical_scores SET valid_to=:now
            WHERE hazard_type='storm' AND scenario='baseline' AND time_horizon='current'
              AND valid_to IS NULL AND shap_factors->>'storm' = :name"""),
            {"now": now, "name": name})
        s.execute(text("""
            INSERT INTO canonical_scores
                (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                 risk_score, risk_bucket, model_version, data_vintage, shap_factors,
                 scored_at, valid_from, valid_to)
            VALUES
                (:score_id,:h3_cell,:h3_resolution,:hazard_type,:scenario,:time_horizon,
                 :risk_score,:risk_bucket,:model_version,:data_vintage, CAST(:shap AS jsonb),
                 :scored_at,:valid_from, NULL)
        """), records)
        exists = s.execute(text("SELECT 1 FROM model_registry WHERE model_version = :mv"),
                            {"mv": MODEL_VERSION}).first()
        if not exists:
            s.execute(text("""
                INSERT INTO model_registry
                    (model_id, model_version, hazard_type, algorithm, training_data_vintage,
                     training_cell_count, is_active, activated_at, created_at)
                VALUES
                    (gen_random_uuid(), :mv, 'storm', 'physics_modified_rankine_vortex',
                     :vintage, :n, true, now(), now())
            """), {"mv": MODEL_VERSION, "vintage": vintage.date(), "n": len(records)})

    rs = np.array([r["risk_score"] for r in records])
    print(f"  wrote {len(records)} storm scores — risk spans {rs.min():.1f}..{rs.max():.1f}")
    return len(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--storm-id", default="2017260N12310", help="IBTrACS storm SID (default: Hurricane Maria)")
    a = ap.parse_args()
    score_storm(a.storm_id)


if __name__ == "__main__":
    main()
