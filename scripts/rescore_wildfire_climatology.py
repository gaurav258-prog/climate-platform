"""Re-score every current STANDING-lane wildfire cell with the calibrated hazard climatology (one version everywhere).

The batch day-of model left current standing rows in canonical_scores for the pre-scored regions; those are what
portfolio views read. This retires them (lane-scoped, append-only) and writes wildfire-climatology-v1 for the same
(cell, scenario, horizon) keys. Pure grid lookups — no fetch. Usage: PYTHONPATH=. .venv/bin/python scripts/rescore_wildfire_climatology.py
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.engine import _retire_previous_scores
from ml.scoring.wildfire_climatology import (
    MODEL_VERSION,
    PRODUCTION_VARIANT,
    load_grids,
    score_point_pure,
)

BATCH = 2000


def main() -> int:
    if load_grids() is None:
        print("climatologies not built"); return 1
    with get_session() as s:
        keys = s.execute(text("""
            SELECT DISTINCT h3_cell, scenario, time_horizon FROM canonical_scores
            WHERE hazard_type='wildfire' AND score_lane='standing' AND valid_to IS NULL AND model_version <> :mv
        """), {"mv": MODEL_VERSION}).all()
    print(f"{len(keys)} current standing wildfire keys from older models → {MODEL_VERSION}")
    now = datetime.now(timezone.utc)
    for i in range(0, len(keys), BATCH):
        chunk = keys[i:i + BATCH]
        rows = []
        for cell, sc, hz in chunk:
            lat, lon = h3.cell_to_latlng(cell)
            r = score_point_pure(lat, lon, PRODUCTION_VARIANT)
            risk = float(r["score"])
            shap = {"tier": "calibrated", "model": MODEL_VERSION, "rescored_from_batch": True,
                    **{k: v for k, v in r.items() if k != "score"}}
            rows.append({"id": str(uuid.uuid4()), "c": cell, "sc": sc, "h": hz, "r": risk, "b": score_to_bucket(risk).value,
                         "mv": MODEL_VERSION, "now": now, "shap": json.dumps(shap)})
        with get_session() as s:
            for sc in {k[1] for k in chunk}:
                _retire_previous_scores(s, [k[0] for k in chunk if k[1] == sc], "wildfire", sc, now, score_lane="standing")
            s.execute(text("""
                INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                    risk_score, risk_bucket, model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to, score_lane)
                VALUES (:id, :c, 8, 'wildfire', :sc, :h, :r, :b, :mv, :now, CAST(:shap AS jsonb), :now, :now, NULL, 'standing')
                ON CONFLICT (h3_cell, hazard_type, scenario, time_horizon, score_lane) WHERE valid_to IS NULL DO NOTHING
            """), rows)
        print(f"  {min(i + BATCH, len(keys))}/{len(keys)}", flush=True)
    with get_session() as s:
        print(s.execute(text("""SELECT model_version, count(*) FROM canonical_scores WHERE hazard_type='wildfire'
                                AND score_lane='standing' AND valid_to IS NULL GROUP BY 1""")).all())
    return 0


if __name__ == "__main__":
    sys.exit(main())
