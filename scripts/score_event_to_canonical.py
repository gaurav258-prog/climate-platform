"""
Score a real flood event into canonical_scores with the multi-event model.

Deploys the validated multi-event flood model end to end: fetch ERA5 (shared
module — same features it was trained on), score every H3 cell, and write to
canonical_scores using the active model version. This is what makes the live UI
reflect the real model instead of the retired single-event one.

Usage:  python scripts/score_event_to_canonical.py "2024 Valencia DANA"
"""
import os
import pickle
import sys
import uuid
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.flood_era5 import FEATURE_COLS, compute_features, fetch_era5

# event catalog (date + area) — reuse the trainer's
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
from build_multievent_flood import EVENTS

MODEL_PKL = "models/flood_multievent/scorer.pkl"


def active_model_version() -> str:
    with get_session() as s:
        row = s.execute(text(
            "SELECT model_version FROM model_registry WHERE hazard_type='flood' AND is_active LIMIT 1"
        )).first()
    return row[0] if row else "flood-multievent"


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "2024 Valencia DANA"
    ev = next((e for e in EVENTS if e["name"] == name), None)
    if ev is None:
        print(f"unknown event '{name}'. Options: {[e['name'] for e in EVENTS]}"); sys.exit(1)

    scorer = pickle.load(open(MODEL_PKL, "rb"))
    version = active_model_version()
    vintage = datetime(ev["peak"].year, ev["peak"].month, ev["peak"].day, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    print(f"scoring '{name}' (peak {ev['peak']}) with {version} …", flush=True)
    ds = fetch_era5(ev["fetch_area"], ev["peak"]); df = compute_features(ds); ds.close()
    df["score"] = scorer.score_dataframe(df[FEATURE_COLS].copy())["score"].values
    print(f"  {len(df)} cells scored — max {df.score.max():.1f}, "
          f"{int((df.score>=50).sum())} HIGH+ (≥50)")

    records = [{
        "score_id": str(uuid.uuid4()), "h3_cell": r.h3_cell, "h3_resolution": 8,
        "hazard_type": "flood", "scenario": "baseline", "time_horizon": "current",
        "risk_score": round(float(r.score), 2), "risk_bucket": score_to_bucket(float(r.score)).value,
        "model_version": version, "data_vintage": vintage, "scored_at": now,
        "valid_from": now,
    } for r in df.itertuples()]

    with get_session() as s:
        # retire current flood/baseline/current scores, then append the new ones
        s.execute(text("""
            UPDATE canonical_scores SET valid_to = :now
            WHERE hazard_type='flood' AND scenario='baseline'
              AND time_horizon='current' AND valid_to IS NULL
        """), {"now": now})
        s.execute(text("""
            INSERT INTO canonical_scores
                (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                 risk_score, risk_bucket, model_version, data_vintage, scored_at, valid_from, valid_to)
            VALUES
                (:score_id, :h3_cell, :h3_resolution, :hazard_type, :scenario, :time_horizon,
                 :risk_score, :risk_bucket, :model_version, :data_vintage, :scored_at, :valid_from, NULL)
        """), records)

    print(f"  wrote {len(records)} canonical_scores (model={version}, vintage={ev['peak']})")


if __name__ == "__main__":
    main()
