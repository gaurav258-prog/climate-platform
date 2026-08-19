"""
Score a recent seismic event into canonical_scores using real physics.

Replaces the degenerate ML scoring (which produced a uniform blanket because its
risk model was a circular fit to a synthetic formula on constant features). Now:
  - per-cell intensity from an Intensity Prediction Equation on hypocentral distance
    (ml/scoring/seismic_physics) → risk VARIES spatially and with event depth
  - a real Omori-Utsu / Reasenberg-Jones aftershock forecast (24h/72h/7d)

A cell takes the MAX intensity over all nearby events, so an aftershock sequence
(many events) reinforces the footprint naturally.

Usage:  python scripts/score_seismic_event.py            # latest large recent event
"""
import json
import sys
import uuid
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.seismic_physics import aftershock_forecast, ipe_mmi, mmi_to_risk

MODEL_VERSION = "seismic-gmpe-ipe-v1"
INFLUENCE_KM = 400.0  # beyond this an event's MMI is negligible


def haversine(la1, lo1, la2, lo2):
    r = 6371.0
    p1, p2 = np.radians(la1), np.radians(la2)
    dp, dl = np.radians(la2 - la1), np.radians(lo2 - lo1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def main():
    with get_session() as s:
        rows = s.execute(text("""
            SELECT CAST(magnitude AS FLOAT) m, CAST(epicentre_lat AS FLOAT) lat,
                   CAST(epicentre_lon AS FLOAT) lon,
                   CAST(COALESCE(depth_km, 10) AS FLOAT) depth, origin_time, region_name
            FROM seismic_events
            WHERE origin_time > now() - interval '14 days'
            ORDER BY magnitude DESC
        """)).mappings().all()
    if not rows:
        print("no recent seismic events"); sys.exit(1)
    events = [dict(r) for r in rows]
    main_ev = events[0]
    print(f"mainshock: M{main_ev['m']} {main_ev['region_name']} "
          f"({main_ev['lat']:.2f},{main_ev['lon']:.2f}) depth {main_ev['depth']:.0f}km")

    centre = h3.latlng_to_cell(main_ev["lat"], main_ev["lon"], 8)
    cells = h3.grid_disk(centre, 55)
    print(f"scoring {len(cells)} real H3 cells with IPE attenuation …")

    # sequence-level aftershock forecast (damaging M>=5), from the mainshock
    af = aftershock_forecast(main_ev["m"], mmin=5.0)
    now = datetime.now(timezone.utc)
    vintage = main_ev["origin_time"]

    records = []
    for cell in cells:
        clat, clon = h3.cell_to_latlng(cell)
        best_mmi, best = 0.0, None
        for e in events:
            d = haversine(clat, clon, e["lat"], e["lon"])
            if d > INFLUENCE_KM:
                continue
            mmi = float(ipe_mmi(e["m"], d, e["depth"]))
            if mmi > best_mmi:
                best_mmi, best = mmi, (e, d)
        risk = float(mmi_to_risk(best_mmi))
        shap = dict(af)
        if best is not None:
            shap.update(mmi=round(best_mmi, 2), driver_mag=best[0]["m"],
                        driver_dist_km=round(best[1], 1))
        records.append({
            "score_id": str(uuid.uuid4()), "h3_cell": cell, "h3_resolution": 8,
            "hazard_type": "seismic", "scenario": "baseline", "time_horizon": "current",
            "risk_score": round(risk, 2), "risk_bucket": score_to_bucket(risk).value,
            "model_version": MODEL_VERSION, "data_vintage": vintage,
            "scored_at": now, "valid_from": now, "shap": json.dumps(shap),
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

    rs = np.array([r["risk_score"] for r in records])
    print(f"wrote {len(records)} seismic scores — risk spans {rs.min():.1f}..{rs.max():.1f} "
          f"(was a flat 88.3 blanket)")
    print(f"aftershock forecast (M>=5): 24h={af['aftershock_24h']:.2f} "
          f"72h={af['aftershock_72h']:.2f} 7d={af['aftershock_7d']:.2f}")


if __name__ == "__main__":
    main()
