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
from ml.scoring.drought_climatology import drought_score
from ml.scoring.heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

MODEL_VERSION = "drought-climatology-v1-seasonal"
CURRENT_YEAR = 2024
NC_TEMPLATE = "data/era5_baseline/{region}_1991_2024_monthly.nc"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", required=True, help="ERA5 baseline region key (regions.py)")
    ap.add_argument("--commodity", required=True, help="snap this commodity's plots (by lat/lon)")
    ap.add_argument("--season", default="4,5,6,7,8", help="drought-window months, comma-separated")
    ap.add_argument("--spei-scale", type=int, default=6, help="SPEI accumulation months (match the fit)")
    args = ap.parse_args()
    season = [int(m) for m in args.season.split(",")]

    ds = load_monthly(NC_TEMPLATE.format(region=args.region))
    spei = compute_indices(ds, scale=args.spei_scale)["spei"]
    seas = spei.sel(time=spei["time.month"].isin(season)).groupby("time.year").mean("time")
    cur = seas.sel(year=CURRENT_YEAR)
    lats, lons = ds["latitude"].values, ds["longitude"].values
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

    if not scored_cells:
        print(f"no cells scored for {args.region} — is the baseline .nc present?")
        return 1

    with get_session() as s:
        # append-only, STANDING lane, THIS region's cells only (never touch other belts or nowcasts)
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

    print(f"{args.region}/{args.commodity}: scored {len(rows)} drought rows over "
          f"{len(scored_cells)} cells; snapped {snapped} plots")
    with get_session() as s:
        for r in s.execute(text("""
            SELECT p.plot_name, ROUND(v.physical_risk_score::numeric,1) score
            FROM sc_sourcing_plots p JOIN sc_commodities co ON co.commodity_id=p.commodity_id
            JOIN v_sc_plot_physical_risk v ON v.plot_id=p.plot_id
            WHERE co.name=:c AND v.hazard_type='drought'
              AND v.scenario='baseline' AND v.time_horizon='current'
        """), {"c": args.commodity}).mappings().all():
            print(f"  {r['plot_name']}: current drought {r['score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
