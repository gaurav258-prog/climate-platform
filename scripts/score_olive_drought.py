"""Score the Spanish olive belt for DROUGHT into the golden source (canonical_scores).

Drought is the validated olive signal (r²=0.51 over 31 years, SPEI-6; see the 'ranged' tier /
scripts/fit_ranged_crop.py). Mirrors scripts/score_cocoa_heat.py exactly in shape — per-cell,
scenario×horizon, append-only, then snap the demo olive plots so olive's COGS-at-risk flips
from "€ pending" to a real drought-driven RANGE.

SCALE CONSISTENCY (the reason this uses SPEI-6 Apr–Aug). The ranged fit regressed olive's
climate-attributable shock on drought_score(SPEI-6 seasonal Apr–Aug) per year. The plot's
"current" score here is drought_score of the SAME index for the latest year — so the score the
engine multiplies through the fit is on the fit's own scale. "current" = 2024 (the latest year,
like cocoa's 2024 heat); forward scenarios shift SPEI drier by warming (drought_climatology's
DRYING_PER_C). A wet current year (2024 was wet in Spain) therefore reads LOW drought risk —
honestly — and the risk rises under projection.

Run (no network — local baseline .nc): .venv/bin/python scripts/score_olive_drought.py
"""
import uuid
from datetime import datetime, timezone

import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.drought import compute_indices, load_monthly
from ml.scoring.drought_climatology import drought_score, DRYING_PER_C
from ml.scoring.heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

NC = "data/era5_baseline/spain_olive_1991_2024_monthly.nc"
MODEL_VERSION = "drought-climatology-v1-seasonal"
CURRENT_YEAR = 2024
SPEI_SCALE = 6                 # the agronomic water-year window the fit uses
SEASON = [4, 5, 6, 7, 8]       # Apr–Aug — olive water-stress window, matches the fit
OLIVE_PLOTS = [("Andalusia Olive oil plot 1", 37.70025, -6.29677),
               ("Andalusia Olive oil plot 2", 37.69856, -4.90123),
               ("Andalusia Olive oil plot 3", 37.69883, -6.69901)]


def main():
    ds = load_monthly(NC)
    spei = compute_indices(ds, scale=SPEI_SCALE)["spei"]
    # seasonal-mean SPEI per cell per year, then the current year's field
    seas = spei.sel(time=spei["time.month"].isin(SEASON)).groupby("time.year").mean("time")
    cur = seas.sel(year=CURRENT_YEAR)
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    now = datetime.now(timezone.utc)
    vintage = datetime(CURRENT_YEAR, 12, 1, tzinfo=timezone.utc)

    rows, scored_cells = [], set()
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            sp = float(cur.values[i, j])
            if np.isnan(sp):
                continue
            cell = h3.latlng_to_cell(float(la), float(lo), 8)
            scored_cells.add(cell)
            for scen in SCENARIO_WARMING_C:
                for horz in HORIZON_FRACTION:
                    sc = drought_score(sp, scen, horz)
                    rows.append({"id": str(uuid.uuid4()), "h3": cell, "res": 8,
                                 "hz": "drought", "scen": scen, "horz": horz,
                                 "score": sc, "bucket": score_to_bucket(sc).value,
                                 "mv": MODEL_VERSION, "dv": vintage, "now": now})

    with get_session() as s:
        # append-only, STANDING lane only: retire prior standing drought scores for these cells.
        # A nowcast (on-demand SPI-1) must never be touched here — see the score_lane invariant.
        s.execute(text("""
            UPDATE canonical_scores SET valid_to = :now
            WHERE hazard_type='drought' AND valid_to IS NULL
              AND COALESCE(score_lane,'standing')='standing'
              AND h3_cell = ANY(:cells)
        """), {"now": now, "cells": list(scored_cells)})
        for k in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, scored_at,
                     valid_from, valid_to, score_lane)
                VALUES (:id,:h3,:res,:hz,:scen,:horz,:score,:bucket,:mv,:dv,:now,:now,NULL,'standing')
            """), rows[k:k + 2000])

        snapped = 0
        for name, lat, lon in OLIVE_PLOTS:
            glat, glon = round(lat * 10) / 10, round(lon * 10) / 10
            cell = h3.latlng_to_cell(glat, glon, 8)
            if cell not in scored_cells:
                cell = min(scored_cells, key=lambda c: (lambda p: (p[0]-lat)**2 + (p[1]-lon)**2)(h3.cell_to_latlng(c)))
            r = s.execute(text("UPDATE sc_sourcing_plots SET h3_cell=:c WHERE plot_name=:n"),
                          {"c": cell, "n": name})
            snapped += r.rowcount

    try:
        with get_session() as s:
            s.execute(text("UPDATE model_registry SET is_active=false WHERE hazard_type='drought' AND model_version=:mv"),
                      {"mv": MODEL_VERSION})
            s.execute(text("""
                INSERT INTO model_registry (model_id, hazard_type, model_version, algorithm,
                    training_data_vintage, validation_note, is_active, created_at)
                VALUES (:id,'drought',:mv,'SPEI-6 seasonal climatology, Phi(-SPEI) percentile',
                    :dv,
                    'Drought is the validated olive signal (ranged tier, r2=0.51 over 31 yrs, SPEI-6 Apr-Aug). Score = Phi(-SPEI6)x100 for the latest year; forward scenarios shift SPEI drier by warming. Published as a RANGE via sc_commodity_fit.',
                    true, :now)
            """), {"id": str(uuid.uuid4()), "mv": MODEL_VERSION, "dv": vintage, "now": now})
    except Exception as e:
        print("  (model_registry insert skipped:", str(e)[:70], ")")

    print(f"scored {len(rows)} drought rows over {len(scored_cells)} olive-belt cells; snapped {snapped} plots")
    with get_session() as s:
        for r in s.execute(text("""
            SELECT p.plot_name, ROUND(v.physical_risk_score::numeric,1) score
            FROM sc_sourcing_plots p JOIN v_sc_plot_physical_risk v ON v.plot_id=p.plot_id
            WHERE p.commodity_id=(SELECT commodity_id FROM sc_commodities WHERE name='Olive oil')
              AND v.hazard_type='drought' AND v.scenario='baseline' AND v.time_horizon='current'
        """)).mappings().all():
            print(f"  {r['plot_name']}: current drought {r['score']}")


if __name__ == "__main__":
    main()
