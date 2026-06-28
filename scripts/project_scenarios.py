"""
Project the baseline golden source forward under NGFS scenarios × time horizons.

TCFD/IFRS S2 require forward-looking scenario analysis, but we only scored
(baseline, current). This amplifies each baseline cell's physical risk by a
warming × time factor so the Scenario / Horizon selectors return real, different
numbers (risk rises under hotter pathways and later horizons).

Method (transparent, illustrative): score' = min(100, baseline_score × (1 + s·h)),
where s is the scenario warming intensity and h the horizon weight. Append-only:
prior projections are retired (valid_to) before inserting fresh ones. Seismic is
geophysical (not climate-scenario dependent) so it is left at baseline/current only.

Run:  .venv/bin/python scripts/project_scenarios.py
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket

# scenario warming intensity (incl. committed warming in 'baseline') and horizon weight
SCEN = {"baseline": 0.06, "orderly_1_5c": 0.12, "disorderly_2c": 0.24, "hot_house_3_5c": 0.45}
HORZ = {"current": 0.0, "2030": 0.3, "2050": 0.6, "2100": 1.0}


def main():
    now = datetime.now(timezone.utc)
    with get_session() as s:
        base = s.execute(text("""
            SELECT h3_cell, hazard_type, CAST(risk_score AS FLOAT) AS score,
                   model_version, data_vintage, COALESCE(h3_resolution, 8) AS res
            FROM   canonical_scores
            WHERE  scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
            AND   (hazard_type='flood'
                   OR (hazard_type='wildfire' AND h3_cell IN (SELECT h3_cell FROM bank_assets)))
        """)).mappings().all()

        # retire previous projections (everything that isn't the real baseline/current)
        s.execute(text("""
            UPDATE canonical_scores SET valid_to = :now
            WHERE  valid_to IS NULL AND hazard_type IN ('flood','wildfire')
            AND    NOT (scenario='baseline' AND time_horizon='current')
        """), {"now": now})

        rows = []
        for b in base:
            for scen, inten in SCEN.items():
                for horz, w in HORZ.items():
                    if scen == "baseline" and horz == "current":
                        continue  # the real scored value — never overwrite
                    score = min(100.0, b["score"] * (1 + inten * w))
                    rows.append({
                        "id": str(uuid.uuid4()), "h3": b["h3_cell"], "res": b["res"],
                        "hz": b["hazard_type"], "scen": scen, "horz": horz,
                        "score": round(score, 2), "bucket": score_to_bucket(score).value,
                        "mv": b["model_version"], "dv": b["data_vintage"], "now": now,
                    })

        for i in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, scored_at, valid_from, valid_to)
                VALUES
                    (:id, :h3, :res, :hz, :scen, :horz, :score, :bucket, :mv, :dv, :now, :now, NULL)
            """), rows[i:i + 2000])

    print(f"projected {len(rows)} scores across "
          f"{len(SCEN) * len(HORZ) - 1} scenario×horizon combos from {len(base)} baseline cells")


if __name__ == "__main__":
    main()
