"""Score the coastal-flood / sea-level-rise hazard for coastal exposure cells.

Only cells within the coastal band (coastal_exposure.is_coastal) with a known elevation are scored —
an inland or high asset has no coastal-flood hazard (the hazard is simply absent for it, never a
fabricated 0-row). Per scenario × horizon: baseline + 'current' hold today's coastal exposure
(no SLR added, no band); the three SSP pathways add AR6 sea-level rise and carry the likely-range
band. Append-only, standing lane.

Run (after scripts.build_coastal_exposure):  .venv/bin/python -m scripts.score_coastal_flood
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.sea_level import (coastal_flood_score, slr_projection, SlrProjection,
                                  SEA_LEVEL_VERSION)

SCENARIOS = ["baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c"]
HORIZONS = ["current", "2030", "2050", "2100"]
HAZARD = "coastal_flood"
_ZERO = SlrProjection(0.0, 0.0, 0.0, 0.0)   # today's sea level (baseline/current: no added SLR)


def main():
    now = datetime.now(timezone.utc)
    with get_session() as s:
        cells = s.execute(text("""
            SELECT h3_cell, elevation_m, dist_to_coast_km
            FROM coastal_exposure WHERE is_coastal = true AND elevation_m IS NOT NULL
        """)).mappings().all()

        s.execute(text("""
            UPDATE canonical_scores SET valid_to = :now
            WHERE hazard_type = :hz AND valid_to IS NULL AND COALESCE(score_lane,'standing')='standing'
              AND h3_cell = ANY(:cells)
        """), {"now": now, "hz": HAZARD, "cells": [c["h3_cell"] for c in cells]})

        rows, banded = [], 0
        for c in cells:
            elev, dist = c["elevation_m"], c["dist_to_coast_km"]
            for scen in SCENARIOS:
                for horz in HORIZONS:
                    slr = slr_projection(scen, horz)
                    if slr is None:                              # baseline / current — today, no band
                        sc, _, _ = coastal_flood_score(elev, dist, _ZERO)
                        lo = hi = None
                    else:
                        sc, lo, hi = coastal_flood_score(elev, dist, slr)
                    if sc is None:
                        continue
                    if lo is not None:
                        banded += 1
                    rows.append({"id": str(uuid.uuid4()), "h3": c["h3_cell"], "res": 8, "hz": HAZARD,
                                 "scen": scen, "horz": horz, "score": sc, "bucket": score_to_bucket(sc).value,
                                 "lo": lo, "hi": hi, "mv": SEA_LEVEL_VERSION, "now": now})

        for i in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, score_ci_lower, score_ci_upper,
                     model_version, data_vintage, scored_at, valid_from, valid_to, score_lane)
                VALUES (:id,:h3,:res,:hz,:scen,:horz,:score,:bucket,:lo,:hi,:mv,:now,:now,:now,NULL,'standing')
            """), rows[i:i + 2000])

    print(f"scored {len(rows)} coastal_flood rows over {len(cells)} coastal cells; {banded} carry an SLR band")


if __name__ == "__main__":
    main()
