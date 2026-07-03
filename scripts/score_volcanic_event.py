"""
Score a volcanic event into canonical_scores using real physics.

Mirrors scripts/score_seismic_event.py exactly: per-cell hazard from a distance-
decay physics function (ml/scoring/volcanic_physics), MAX over any nearby event,
write to canonical_scores with hazard_type='volcanic', retire prior rows, register
in model_registry.

GVP's Holocene_Eruptions layer logs eruptive EPISODES (Fuego's whole 2002-present
episode is one row, VEI 3 max) rather than daily-dated sub-events, so unlike
seismic (which reads origin_time straight off seismic_events) this script is
pointed at a specific historical BACKTEST_EVENT (volcano + a target date carried
as external knowledge, e.g. Fuego's well-documented 2018-06-03 paroxysm) rather
than "the latest event in the last N days". See docs/VOLCANIC_HAZARD_METHODOLOGY.md.

Hazard-zone radii come from volcanic_hazard_zones (curated, published sources)
when available, falling back to VEI-scaled defaults (ml.scoring.volcanic_physics.
vei_to_zone_radii) otherwise — flagged in shap_factors either way so it's visible
which volcanoes are on real published radii vs. an estimate.

Usage:  python scripts/score_volcanic_event.py                    # curated backtest set
        python scripts/score_volcanic_event.py --volcano-number 342090
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime, timezone

import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.volcanic_physics import blended_volcanic_score, vei_to_zone_radii

MODEL_VERSION = "volcanic-gvp-physics-v1"
INFLUENCE_KM = 100.0   # beyond this a volcano's ashfall score is low-signal (<~L bucket)

# km-per-ring for H3 grid_disk, derived from the actual hexagon edge length (NOT
# assumed from another script) — with a 20% safety margin so grid_disk(k) reliably
# covers INFLUENCE_KM in every direction, not just along the ring's short axis.
_KM_PER_RING = h3.average_hexagon_edge_length(8, unit="km") * (3 ** 0.5) * 1.2
GRID_DISK_K = int(np.ceil(INFLUENCE_KM / _KM_PER_RING))

# GVP's coarse eruption-episode rows don't isolate the specific historical paroxysm
# date needed for a backtest — these are carried as external, well-documented
# knowledge (see docs/VOLCANIC_HAZARD_METHODOLOGY.md §backtest targets).
BACKTEST_EVENTS = {
    342090: {"name": "Fuego", "date": date(2018, 6, 3), "vei": 3},   # 2018 paroxysm
    273070: {"name": "Taal", "date": date(2020, 1, 12), "vei": 4},   # matches GVP's own start date
}


def haversine(la1, lo1, la2, lo2):
    r = 6371.0
    p1, p2 = np.radians(la1), np.radians(la2)
    dp, dl = np.radians(la2 - la1), np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _zone_radii(session, volcano_number: int, vei: float) -> tuple[float, float, str]:
    rows = session.execute(text("""
        SELECT zone_type, CAST(radius_km AS FLOAT) radius_km, source
        FROM volcanic_hazard_zones WHERE volcano_number = :v
    """), {"v": volcano_number}).mappings().all()
    zones = {r["zone_type"]: r for r in rows}
    if "proximal" in zones and "ashfall" in zones:
        return (zones["proximal"]["radius_km"], zones["ashfall"]["radius_km"],
                f"curated:{zones['proximal']['source']}")
    r_prox, r_ash = vei_to_zone_radii(vei)
    return r_prox, r_ash, "vei_scaled_fallback"


def score_volcano(volcano_number: int):
    info = BACKTEST_EVENTS.get(volcano_number)
    if not info:
        print(f"  volcano {volcano_number}: not in BACKTEST_EVENTS, skipping")
        return 0

    with get_session() as s:
        v = s.execute(text("""
            SELECT volcano_name, CAST(epicentre_lat AS FLOAT) lat, CAST(epicentre_lon AS FLOAT) lon
            FROM volcanic_events WHERE volcano_number = :v LIMIT 1
        """), {"v": volcano_number}).mappings().first()
        if not v:
            print(f"  volcano {volcano_number}: no volcanic_events row — run ingest_gvp_volcanic.py first")
            return 0
        r_prox, r_ash, radii_source = _zone_radii(s, volcano_number, info["vei"])

    name, vlat, vlon = v["volcano_name"], v["lat"], v["lon"]
    print(f"scoring {name} ({volcano_number}) @ ({vlat:.4f},{vlon:.4f}) "
          f"VEI {info['vei']}, target date {info['date']} — "
          f"r_proximal={r_prox:.1f}km r_ash={r_ash:.1f}km [{radii_source}]")

    centre = h3.latlng_to_cell(vlat, vlon, 8)
    cells = h3.grid_disk(centre, GRID_DISK_K)
    print(f"  scoring {len(cells)} H3 cells within ~{INFLUENCE_KM:.0f}km …")

    now = datetime.now(timezone.utc)
    vintage = datetime.combine(info["date"], datetime.min.time()).replace(tzinfo=timezone.utc)

    records = []
    for cell in cells:
        clat, clon = h3.cell_to_latlng(cell)
        d = float(haversine(clat, clon, vlat, vlon))
        if d > INFLUENCE_KM:
            continue
        blended, prox, ash = blended_volcanic_score(d, r_prox, r_ash)
        risk = float(blended)
        shap = {
            "volcano": name, "vei": info["vei"], "driver_dist_km": round(d, 1),
            "proximal_score": round(float(prox), 1), "ashfall_score": round(float(ash), 1),
            "radii_source": radii_source,
        }
        records.append({
            "score_id": str(uuid.uuid4()), "h3_cell": cell, "h3_resolution": 8,
            "hazard_type": "volcanic", "scenario": "baseline", "time_horizon": "current",
            "risk_score": round(risk, 2), "risk_bucket": score_to_bucket(risk).value,
            "model_version": MODEL_VERSION, "data_vintage": vintage,
            "scored_at": now, "valid_from": now, "shap": json.dumps(shap),
        })

    with get_session() as s:
        s.execute(text("""UPDATE canonical_scores SET valid_to=:now
            WHERE hazard_type='volcanic' AND scenario='baseline' AND time_horizon='current'
              AND valid_to IS NULL AND shap_factors->>'volcano' = :name"""),
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
        # Register the model version if this is the first time we've written it.
        exists = s.execute(text("SELECT 1 FROM model_registry WHERE model_version = :mv"),
                            {"mv": MODEL_VERSION}).first()
        if not exists:
            s.execute(text("""
                INSERT INTO model_registry
                    (model_id, model_version, hazard_type, algorithm, training_data_vintage,
                     training_cell_count, is_active, activated_at, created_at)
                VALUES
                    (gen_random_uuid(), :mv, 'volcanic', 'physics_ipe_analogue_proximal_ashfall',
                     :vintage, :n, true, now(), now())
            """), {"mv": MODEL_VERSION, "vintage": vintage.date(), "n": len(records)})

    rs = np.array([r["risk_score"] for r in records])
    print(f"  wrote {len(records)} volcanic scores — risk spans {rs.min():.1f}..{rs.max():.1f}")
    return len(records)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--volcano-number", type=int, default=None,
                     help="score just this GVP volcano number (default: curated backtest set)")
    a = ap.parse_args()
    targets = [a.volcano_number] if a.volcano_number else list(BACKTEST_EVENTS)
    for num in targets:
        score_volcano(num)


if __name__ == "__main__":
    main()
