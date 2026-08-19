"""Project flood / storm / wildfire forward under NGFS scenarios × horizons — CMIP6-driven (v2).

Supersedes the old flat `score × (1 + warming_intensity × horizon_weight)` uplift, which had no
physical basis and no uncertainty. Each exposure cell is now projected from its OWN local CMIP6
warming + precip change (the global delta field, scripts/build_cmip6_global.py) through a documented,
cited per-hazard sensitivity (ml/scoring/physical_projection.py), and carries a real across-model
band in score_ci_lower/upper.

Scope: cells that host actual exposure (financial assets, own sites, sourcing plots) — the cells the
Scenario/Horizon selectors and portfolio projections consume — not the whole globe. Append-only:
prior projections (anything that isn't the real baseline/current) are retired before inserting fresh.

  baseline (NGFS current-policies) has no CMIP6 SSP mapping and 'current' is 0 warming → both are held
  at today's hazard (no fabricated baseline warming). The three SSP-mapped pathways carry the modelled
  change + band. Seismic/volcanic are geophysical (not projected); drought/soil-water/heat have their
  own climatology paths.

Run (after scripts/build_cmip6_global.py):  .venv/bin/python -m scripts.project_scenarios
"""
import json
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.scoring.cmip6 import cmip6_delta_latlon
from ml.scoring.physical_projection import PROJECTION_VERSION, SENSITIVITY, project

HAZARDS = list(SENSITIVITY)                       # flood, storm, wildfire
SCENARIOS = ["baseline", "orderly_1_5c", "disorderly_2c", "hot_house_3_5c"]
HORIZONS = ["current", "2030", "2050", "2100"]
ASSET_TABLES = ["portfolio_entities", "bank_assets", "realestate_properties",
                "sc_company_sites", "sc_sourcing_plots"]


def _asset_cells(s) -> list:
    cells = set()
    for t in ASSET_TABLES:
        try:
            for c in s.execute(text(f"SELECT DISTINCT h3_cell FROM {t} WHERE h3_cell IS NOT NULL")).scalars():
                cells.add(c)
        except Exception:
            pass
    return list(cells)


def main():
    now = datetime.now(timezone.utc)
    with get_session() as s:
        cells = _asset_cells(s)
        base = s.execute(text("""
            SELECT h3_cell, hazard_type, CAST(risk_score AS FLOAT) AS score,
                   model_version, data_vintage, COALESCE(h3_resolution, 8) AS res
            FROM   canonical_scores
            WHERE  scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
              AND  COALESCE(score_lane,'standing')='standing'
              AND  hazard_type = ANY(:hz) AND h3_cell = ANY(:cells)
        """), {"hz": HAZARDS, "cells": cells}).mappings().all()

        # retire previous projections (everything that isn't the real baseline/current) for these hazards
        s.execute(text("""
            UPDATE canonical_scores SET valid_to = :now
            WHERE  valid_to IS NULL AND hazard_type = ANY(:hz)
              AND  COALESCE(score_lane,'standing')='standing'
              AND  NOT (scenario='baseline' AND time_horizon='current')
        """), {"now": now, "hz": HAZARDS})

        rows, banded = [], 0
        for b in base:
            lat, lon = h3.cell_to_latlng(b["h3_cell"])
            for scen in SCENARIOS:
                for horz in HORIZONS:
                    if scen == "baseline" and horz == "current":
                        continue  # the real scored value — never overwrite
                    # baseline (no SSP) and 'current' (0 warming) are held at today's hazard, no band
                    delta = cmip6_delta_latlon(lat, lon, scen, horz)
                    score, lo, hi = project(b["score"], b["hazard_type"], delta)
                    if lo is not None:
                        banded += 1
                    # stamp HOW this forward value was produced (base row carries only the hazard's mv)
                    shap = json.dumps({"projection": PROJECTION_VERSION, "base_score": b["score"],
                                       "cmip6_covered": delta is not None,
                                       "method": "local CMIP6 warming/precip × cited per-hazard elasticity"
                                       if delta is not None else "held flat (no CMIP6 SSP mapping)"})
                    rows.append({
                        "id": str(uuid.uuid4()), "h3": b["h3_cell"], "res": b["res"],
                        "hz": b["hazard_type"], "scen": scen, "horz": horz,
                        "score": round(score, 2), "bucket": score_to_bucket(score).value,
                        "lo": lo, "hi": hi, "mv": b["model_version"], "dv": b["data_vintage"],
                        "shap": shap, "now": now,
                    })

        for i in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, score_ci_lower, score_ci_upper,
                     model_version, data_vintage, shap_factors, scored_at, valid_from, valid_to, score_lane)
                VALUES
                    (:id,:h3,:res,:hz,:scen,:horz,:score,:bucket,:lo,:hi,:mv,:dv,CAST(:shap AS jsonb),:now,:now,NULL,'standing')
            """), rows[i:i + 2000])

    print(f"projected {len(rows)} rows over {len(base)} (cell×hazard) from {len(cells)} exposure cells; "
          f"{banded} carry a CMIP6 model-disagreement band")


if __name__ == "__main__":
    main()
