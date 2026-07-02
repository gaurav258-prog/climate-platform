"""
Score the West-Africa cocoa belt for HEAT into the golden source (canonical_scores),
from the real ERA5-Land baseline. Heat is the validated cocoa signal (see
scripts/backtest_cocoa_drought.py). Then snap the demo cocoa plots onto scored cells so
cocoa's COGS-at-risk flips from "€ pending" to a real, heat-driven number.

Score = Φ(z)×100 vs the 1991–2020 normal (ml/scoring/heat_climatology). "current" uses
the latest year (2024); forward scenarios add warming °C (physically grounded). Append-only.
Run (no network — uses the local baseline .nc): .venv/bin/python scripts/score_cocoa_heat.py
"""
import uuid
from datetime import datetime, timezone

import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.drought import load_monthly
from ml.scoring.heat_climatology import heat_score, SCENARIO_WARMING_C, HORIZON_FRACTION

NC = "data/era5_baseline/west_africa_cocoa_1991_2024_monthly.nc"
MODEL_VERSION = "heat-climatology-v1-seasonal"
CURRENT_YEAR = 2024
# Cocoa heat-stress window: the Jan–Mar harmattan dry season, when developing pods of the
# main crop are hit by hot dry winds (the acute driver of the 2023/24 failure). Seasonal is
# more physically meaningful than an annual mean.
SEASON = [1, 2, 3]
COCOA_PLOTS = [("Ashanti (Ghana) cocoa plot", 6.75, -1.62),
               ("Sud-Comoé (Côte d'Ivoire) cocoa plot", 6.10, -3.20)]


def main():
    ds = load_monthly(NC)
    # seasonal (harmattan) mean per year, not annual — the biologically relevant window
    Tseas = ds["T"].sel(time=ds["time.month"].isin(SEASON)).groupby("time.year").mean("time")
    clim = Tseas.sel(year=slice(1991, 2020))
    cmean = clim.mean("year"); cstd = clim.std("year")
    Tcur = Tseas.sel(year=CURRENT_YEAR)
    lats = ds["latitude"].values; lons = ds["longitude"].values
    now = datetime.now(timezone.utc)
    vintage = datetime(CURRENT_YEAR, 12, 1, tzinfo=timezone.utc)  # data_vintage is a timestamp

    rows = []
    scored_cells = set()
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            tc = float(Tcur.values[i, j]); m = float(cmean.values[i, j]); sd = float(cstd.values[i, j])
            if np.isnan(tc) or np.isnan(m) or np.isnan(sd) or sd <= 0:
                continue
            cell = h3.latlng_to_cell(float(la), float(lo), 8)
            scored_cells.add(cell)
            for scen in SCENARIO_WARMING_C:
                for horz in HORIZON_FRACTION:
                    sc = heat_score(tc, m, sd, scen, horz)
                    rows.append({"id": str(uuid.uuid4()), "h3": cell, "res": 8,
                                 "hz": "heat_acute", "scen": scen, "horz": horz,
                                 "score": sc, "bucket": score_to_bucket(sc).value,
                                 "mv": MODEL_VERSION, "dv": vintage, "now": now})

    with get_session() as s:
        # append-only: retire any prior heat_acute scores
        s.execute(text("UPDATE canonical_scores SET valid_to=:now WHERE hazard_type='heat_acute' AND valid_to IS NULL"),
                  {"now": now})
        for k in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores
                    (score_id, h3_cell, h3_resolution, hazard_type, scenario, time_horizon,
                     risk_score, risk_bucket, model_version, data_vintage, scored_at, valid_from, valid_to)
                VALUES (:id,:h3,:res,:hz,:scen,:horz,:score,:bucket,:mv,:dv,:now,:now,NULL)
            """), rows[k:k + 2000])

        # snap demo cocoa plots to the nearest scored ERA5 gridpoint cell
        snapped = 0
        for name, lat, lon in COCOA_PLOTS:
            glat, glon = round(lat * 10) / 10, round(lon * 10) / 10   # nearest 0.1° gridpoint
            cell = h3.latlng_to_cell(glat, glon, 8)
            if cell not in scored_cells:
                # fall back: nearest scored cell by centroid
                cell = min(scored_cells, key=lambda c: (lambda p: (p[0]-lat)**2 + (p[1]-lon)**2)(h3.cell_to_latlng(c)))
            r = s.execute(text("UPDATE sc_sourcing_plots SET h3_cell=:c WHERE plot_name=:n"),
                          {"c": cell, "n": name})
            snapped += r.rowcount

    # register the model in a SEPARATE transaction (best-effort; provenance also on each score row)
    try:
        with get_session() as s:
            s.execute(text("UPDATE model_registry SET is_active=false WHERE hazard_type='heat_acute'"))
            s.execute(text("""
                INSERT INTO model_registry (model_id, hazard_type, model_version, algorithm,
                    training_data_vintage, validation_note, is_active, created_at)
                VALUES (:id,'heat_acute',:mv,'climatology two-part (absolute stress + anomaly)',
                    :dv,
                    'Blend of cocoa thermal-stress band (25-31C) and standardized anomaly vs 1991-2020; forward scenarios add warming C. Heat is the validated cocoa signal (2023/24 = hottest year in 34). Absolute Tmax>32C pod-fill thresholds = refinement.',
                    true, :now)
            """), {"id": str(uuid.uuid4()), "mv": MODEL_VERSION, "dv": vintage, "now": now})
    except Exception as e:
        print("  (model_registry insert skipped:", str(e)[:70], ")")

    print(f"scored {len(rows)} heat rows over {len(scored_cells)} cocoa-belt cells "
          f"({len(SCENARIO_WARMING_C)}×{len(HORIZON_FRACTION)} scenario×horizon)")
    # quick read-back: cocoa plots' current heat
    with get_session() as s:
        for r in s.execute(text("""
            SELECT p.plot_name, ROUND(v.physical_risk_score::numeric,1) score
            FROM sc_sourcing_plots p JOIN v_sc_plot_physical_risk v ON v.plot_id=p.plot_id
            WHERE p.commodity_id=(SELECT commodity_id FROM sc_commodities WHERE name='Cocoa')
              AND v.scenario='baseline' AND v.time_horizon='current'
        """)).mappings().all():
            print(f"  {r['plot_name']}: heat {r['score']}")
    print(f"snapped {snapped} cocoa plots onto scored cells")


if __name__ == "__main__":
    main()
