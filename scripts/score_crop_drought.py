"""Score ANY crop region for DROUGHT into the golden source — the reusable, parametric version.

Generalises scripts/score_olive_drought.py: region, commodity, season and SPEI scale are all
arguments, and plots are snapped by their STORED lat/lon (not hard-coded coordinates), so the
same audited path serves every crop. Per-cell, scenario×horizon, append-only in the STANDING
lane (nowcasts untouched — the score_lane invariant), scoped to THIS region's cells only so
scoring one belt never retires another's.

SCALE CONSISTENCY. Pass the SAME --season / --spei-scale the ranged fit used for this crop, so
the plot's standing drought score is on the fit's own scale. "current" = the latest year;
forward scenarios shift SPEI drier by warming (drought_climatology's DRYING_PER_C). A wet
current year reads LOW drought risk — honestly — and risk rises under projection.

    python -m scripts.score_crop_drought --region spain_beet --commodity "Sugar beet" \
        --season 4,5,6,7,8 --spei-scale 6
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone

import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.drought import compute_indices, load_monthly
from ml.features import soil_moisture as smf
from ml.scoring.drought_climatology import drought_score
from ml.scoring.soil_water_climatology import soil_water_score
from ml.scoring.heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

CURRENT_YEAR = 2024
NC_TEMPLATE = "data/era5_baseline/{region}_1991_2024_monthly.nc"
SM_TEMPLATE = "data/era5_baseline/{region}_1991_2024_soilmoisture.nc"
# per driver: the hazard_type written to canonical_scores + the model_version tag
DRIVERS = {
    "drought": ("drought", "drought-climatology-v1-seasonal"),
    "soil_water": ("soil_water", "soil-water-climatology-v1-seasonal"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, help="ERA5 baseline region key (regions.py)")
    ap.add_argument("--commodity", required=True, help="snap this commodity's plots (by lat/lon)")
    ap.add_argument("--driver", default="drought", choices=list(DRIVERS),
                    help="drought (SPEI) or soil_water (root-zone soil-moisture anomaly)")
    ap.add_argument("--season", default="4,5,6,7,8", help="stress-window months, comma-separated")
    ap.add_argument("--spei-scale", type=int, default=6, help="SPEI accumulation months (drought only)")
    args = ap.parse_args()
    season = [int(m) for m in args.season.split(",")]
    hazard_type, MODEL_VERSION = DRIVERS[args.driver]

    # per-cell current-year seasonal index → 0-100 stress score under each scenario×horizon
    if args.driver == "drought":
        ds = load_monthly(NC_TEMPLATE.format(region=args.region))
        idx = compute_indices(ds, scale=args.spei_scale)["spei"]
        score_fn = drought_score
    else:
        idx = smf.anomaly(smf.load_root_zone(SM_TEMPLATE.format(region=args.region)))
        score_fn = soil_water_score
    seas = idx.sel(time=idx["time.month"].isin(season)).groupby("time.year").mean("time")
    cur = seas.sel(year=CURRENT_YEAR)
    lats, lons = idx["latitude"].values, idx["longitude"].values
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
                    sc = score_fn(sp, scen, horz)
                    rows.append({"id": str(uuid.uuid4()), "h3": cell, "res": 8,
                                 "hz": hazard_type, "scen": scen, "horz": horz,
                                 "score": sc, "bucket": score_to_bucket(sc).value,
                                 "mv": MODEL_VERSION, "dv": vintage, "now": now})

    if not scored_cells:
        print(f"no cells scored for {args.region} — is the baseline .nc present?")
        return 1

    with get_session() as s:
        # append-only, STANDING lane, THIS region's cells + THIS hazard only (never touch another
        # belt, another hazard on the same cell, or a nowcast)
        s.execute(text("""
            UPDATE canonical_scores SET valid_to = :now
            WHERE hazard_type=:hz AND valid_to IS NULL
              AND COALESCE(score_lane,'standing')='standing'
              AND h3_cell = ANY(:cells)
        """), {"now": now, "hz": hazard_type, "cells": list(scored_cells)})
        for k in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, scored_at,
                     valid_from, valid_to, score_lane)
                VALUES (:id,:h3,:res,:hz,:scen,:horz,:score,:bucket,:mv,:dv,:now,:now,NULL,'standing')
            """), rows[k:k + 2000])

        # snap this commodity's plots to the nearest scored cell by their stored coordinates
        plots = s.execute(text("""
            SELECT p.plot_name, p.latitude, p.longitude
            FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id = p.commodity_id
            WHERE co.name = :c AND p.latitude IS NOT NULL
        """), {"c": args.commodity}).fetchall()
        snapped = 0
        for name, lat, lon in plots:
            lat, lon = float(lat), float(lon)
            glat, glon = round(lat * 10) / 10, round(lon * 10) / 10
            cell = h3.latlng_to_cell(glat, glon, 8)
            if cell not in scored_cells:
                cell = min(scored_cells,
                           key=lambda c: (lambda p: (p[0]-lat)**2 + (p[1]-lon)**2)(h3.cell_to_latlng(c)))
            r = s.execute(text("UPDATE sc_sourcing_plots SET h3_cell=:c WHERE plot_name=:n"),
                          {"c": cell, "n": name})
            snapped += r.rowcount

    # register/refresh this hazard's active climatology model (reproducible; mirrors score_cocoa_heat)
    try:
        with get_session() as s:
            s.execute(text("UPDATE model_registry SET is_active=false WHERE hazard_type=:hz"),
                      {"hz": hazard_type})
            s.execute(text("""
                INSERT INTO model_registry (model_id, hazard_type, model_version, algorithm,
                    training_data_vintage, validation_note, is_active, created_at)
                VALUES (:id,:hz,:mv,:alg,:dv,:note,true,:now)
            """), {"id": str(uuid.uuid4()), "hz": hazard_type, "mv": MODEL_VERSION,
                   "alg": ("SPEI seasonal climatology, Phi(-SPEI)x100" if args.driver == "drought"
                           else "root-zone soil-moisture anomaly, Phi(-z)x100"),
                   "dv": vintage,
                   "note": (f"{hazard_type} standing climatology (season {args.season}); latest-year "
                            "score, forward scenarios shift drier with warming. Append-only, standing lane."),
                   "now": now})
    except Exception as e:
        print("  (model_registry insert skipped:", str(e)[:70], ")")

    print(f"{args.region}/{args.commodity}: scored {len(rows)} {hazard_type} rows over "
          f"{len(scored_cells)} cells; snapped {snapped} plots")
    with get_session() as s:
        for r in s.execute(text("""
            SELECT p.plot_name, ROUND(v.physical_risk_score::numeric,1) score
            FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id=p.commodity_id
            JOIN v_sc_plot_physical_risk v ON v.plot_id=p.plot_id
            WHERE co.name=:c AND v.hazard_type=:hz
              AND v.scenario='baseline' AND v.time_horizon='current'
        """), {"c": args.commodity, "hz": hazard_type}).mappings().all():
            print(f"  {r['plot_name']}: current {hazard_type} {r['score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
