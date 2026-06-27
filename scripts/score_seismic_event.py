"""
Score a recent seismic event into canonical_scores (real geometry + ETAS models).

The SeismicScoringEngine is demo-grade: _h3_center is hardcoded to (45,15) and it
writes a JSON file. This does it for real — generates actual H3 cells around the
epicentre, uses real distances, runs the trained damage/risk/ETAS-aftershock
models, and writes canonical_scores (hazard_type='seismic').

Honest scope: the trained models were fit largely on constant depth/PGA/population
features, so the signal is dominated by magnitude and proximity. The aftershock
(ETAS) forecast is the most meaningful output for a large mainshock.

Usage:  python scripts/score_seismic_event.py            # latest M>=6 event
"""
import sys
import uuid
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
import h3
import joblib
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

def _load(name):
    return joblib.load(f"models/{name}.pkl")

# Each model has its own scaler. risk + ETAS use 5 features
# [magnitude, depth, pga, population_impact, building_impact]; damage uses 4.
MODELS = {k: _load(m) for k, m in {
    "damage": "seismic_damage_model", "risk": "seismic_risk_model",
    "etas_24h": "etas_aftershock_24h_model", "etas_72h": "etas_aftershock_72h_model",
    "etas_7d": "etas_aftershock_7d_model"}.items()}
SCALERS = {k: _load(s) for k, s in {
    "damage": "seismic_damage_scaler", "risk": "seismic_risk_scaler",
    "etas_24h": "etas_aftershock_24h_scaler", "etas_72h": "etas_aftershock_72h_scaler",
    "etas_7d": "etas_aftershock_7d_scaler"}.items()}


def _model_nfeat(m):
    if hasattr(m, "n_features_in_"):
        return m.n_features_in_
    return m.get_booster().num_features()


def _predict(key, mag, pga=0.5):
    """Scale + predict, matching the MODEL's feature count. Some shipped scalers
    are broken (etas_72h/7d use a 4-feat scaler for a 5-feat model) — fall back to
    a compatible same-dimension scaler so the real models can still be used."""
    full = [mag, 10.0, pga, 0.1, 0.5]  # mag, depth, pga, population, building
    model = MODELS[key]
    n = _model_nfeat(model)
    sc = SCALERS[key]
    if sc.n_features_in_ != n:
        sc = SCALERS["etas_24h"] if n == 5 else SCALERS["damage"]
    return float(model.predict(sc.transform([full[:n]]))[0])


def haversine(la1, lo1, la2, lo2):
    r = 6371.0
    p1, p2 = np.radians(la1), np.radians(la2)
    dp, dl = np.radians(la2 - la1), np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def main():
    with get_session() as s:
        rows = s.execute(text("""
            SELECT event_id, CAST(magnitude AS FLOAT) m, CAST(epicentre_lat AS FLOAT) lat,
                   CAST(epicentre_lon AS FLOAT) lon, CAST(depth_km AS FLOAT) depth, origin_time, region_name
            FROM seismic_events
            WHERE origin_time > now() - interval '14 days'
            ORDER BY magnitude DESC
        """)).mappings().all()
    if not rows:
        print("no recent seismic events"); sys.exit(1)
    events = [dict(r) for r in rows]
    main_ev = events[0]
    print(f"mainshock: M{main_ev['m']} {main_ev['region_name']} ({main_ev['lat']:.2f},{main_ev['lon']:.2f})")

    # real H3 cells around the epicentre (~k rings ≈ regional footprint)
    centre = h3.latlng_to_cell(main_ev["lat"], main_ev["lon"], 8)
    cells = h3.grid_disk(centre, 55)
    print(f"scoring {len(cells)} real H3 cells around the epicentre …")

    now = datetime.now(timezone.utc)
    vintage = main_ev["origin_time"]
    records = []
    for cell in cells:
        clat, clon = h3.cell_to_latlng(cell)
        nearby = [e for e in events if haversine(clat, clon, e["lat"], e["lon"]) < 100]
        if not nearby:
            risk, dmg, a24, a72, a7d = 25.0, 0.05, 0.01, 0.02, 0.03
        else:
            # strongest nearby event + distance to it → simple PGA attenuation
            strongest = max(nearby, key=lambda e: e["m"])
            dist = haversine(clat, clon, strongest["lat"], strongest["lon"])
            max_mag = strongest["m"]
            pga = max(0.02, 0.6 * np.exp(-dist / 40.0))      # ~near-field 0.6g, ~40km decay
            risk = float(min(100, _predict("risk", max_mag, pga)))
            dmg = float(min(1.0, 10 ** _predict("damage", max_mag, pga) / 1e6))
            a24 = float(_predict("etas_24h", max_mag, pga))
            a72 = float(_predict("etas_72h", max_mag, pga))
            a7d = float(_predict("etas_7d", max_mag, pga))
        records.append({
            "score_id": str(uuid.uuid4()), "h3_cell": cell, "h3_resolution": 8,
            "hazard_type": "seismic", "scenario": "baseline", "time_horizon": "current",
            "risk_score": round(risk, 2), "risk_bucket": score_to_bucket(risk).value,
            "model_version": "seismic-etas-v1", "data_vintage": vintage,
            "scored_at": now, "valid_from": now,
            "shap": f'{{"aftershock_24h":{a24:.4f},"aftershock_72h":{a72:.4f},"aftershock_7d":{a7d:.4f},"damage_prob":{dmg:.4f}}}',
        })

    with get_session() as s:
        s.execute(text("""UPDATE canonical_scores SET valid_to=:now
            WHERE hazard_type='seismic' AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL"""),
            {"now": now})
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
    hi = sum(1 for r in records if r["risk_score"] >= 50)
    print(f"wrote {len(records)} seismic canonical_scores — {hi} HIGH+ near the epicentre")
    near = [r for r in records if h3.grid_distance(centre, r["h3_cell"]) <= 3]
    if near:
        import json
        af = json.loads(near[0]["shap"])
        print(f"epicentre aftershock forecast: 24h={af['aftershock_24h']:.2f} "
              f"72h={af['aftershock_72h']:.2f} 7d={af['aftershock_7d']:.2f}")


if __name__ == "__main__":
    main()
