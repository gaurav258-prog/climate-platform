"""
Wire Brazil ARABICA coffee into the Terra Foods demo on its validated DROUGHT signal.

1. add a Coffee commodity + a coffee SKU + BOM + supplier + Brazil sourcing plots;
2. score Brazil coffee DROUGHT (SPEI) into canonical_scores (append-only, scenario×horizon);
3. snap the coffee plots onto scored cells so coffee shows a real, drought-driven COGS-at-risk.
Frost (the other 2021 driver) is scored separately by scripts/wire_frost_demo.py, once the
CDS daily-min fix (raw-hourly + local aggregation, see ml/features/frost.py) lands data.
Idempotent. Run: .venv/bin/python scripts/wire_coffee_demo.py

ORG was 33333333-... (Stellar Logistics REIT's id) until 2026-07 -- a stale leftover from
before scripts/fix_terra_foods_org_split.py gave Terra Foods its own dedicated org_id
(55555555-...). That cleanup deleted every sc_* row living under Stellar's org (including
whatever this script had created there), but this script's ORG constant was never updated
to follow -- so Coffee silently vanished from the live Terra Foods demo. Fixed here.
"""
import uuid
from datetime import datetime, timezone

import h3
import numpy as np
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.drought import load_monthly, compute_indices
from ml.scoring.drought_climatology import drought_score, SCENARIO_WARMING_C, HORIZON_FRACTION

ORG = "55555555-5555-4555-8555-555555555555"
NC = "data/era5_baseline/brazil_coffee_1991_2024_monthly.nc"
MODEL_VERSION = "drought-spei-v0"
CURRENT_YEAR = 2024
PLOTS = [("Sul de Minas coffee", -21.6, -45.9), ("Cerrado Mineiro coffee", -19.0, -47.0),
         ("Mogiana (SP) coffee", -20.9, -47.0)]


def main():
    now = datetime.now(timezone.utc)
    vintage = datetime(CURRENT_YEAR, 12, 1, tzinfo=timezone.utc)

    # --- 1. graph: commodity + product + supplier + BOM ---
    with get_session() as s:
        cid = s.execute(text("""
            INSERT INTO sc_commodities (name, hs_code, eudr_covered, demand_elasticity, primary_hazards, global_share_note)
            VALUES ('Coffee','0901',true,-0.28,'drought,frost','Brazil ~35% of world arabica')
            ON CONFLICT (name) DO UPDATE SET demand_elasticity=EXCLUDED.demand_elasticity,
                primary_hazards=EXCLUDED.primary_hazards, global_share_note=EXCLUDED.global_share_note
            RETURNING commodity_id
        """)).scalar()
        # clean prior coffee demo rows (idempotent)
        s.execute(text("DELETE FROM sc_bom_lines WHERE commodity_id=:c AND product_id IN (SELECT product_id FROM sc_products WHERE org_id=:o)"), {"c": cid, "o": ORG})
        s.execute(text("DELETE FROM sc_sourcing_plots WHERE org_id=:o AND commodity_id=:c"), {"o": ORG, "c": cid})
        s.execute(text("DELETE FROM sc_suppliers WHERE org_id=:o AND commodity_id=:c"), {"o": ORG, "c": cid})
        s.execute(text("DELETE FROM sc_products WHERE org_id=:o AND name='Cold Brew Coffee 1L'"), {"o": ORG})

        pid = s.execute(text("""
            INSERT INTO sc_products (product_id, org_id, name, category, annual_units, annual_revenue_eur, annual_cogs_eur)
            VALUES (:id,:o,'Cold Brew Coffee 1L','Beverages',20000000,64000000,42000000) RETURNING product_id
        """), {"id": str(uuid.uuid4()), "o": ORG}).scalar()
        sup = s.execute(text("""
            INSERT INTO sc_suppliers (supplier_id, org_id, name, commodity_id, tier, country)
            VALUES (:id,:o,'Arabica Co-op',:c,1,'BR') RETURNING supplier_id
        """), {"id": str(uuid.uuid4()), "o": ORG, "c": cid}).scalar()
        s.execute(text("""
            INSERT INTO sc_bom_lines (product_id, commodity_id, cost_share_pct, annual_spend_eur)
            VALUES (:p,:c,55,22000000)
            ON CONFLICT (product_id, commodity_id) DO UPDATE SET annual_spend_eur=EXCLUDED.annual_spend_eur
        """), {"p": pid, "c": cid})

    # --- 2. score Brazil coffee drought into canonical_scores ---
    idx = compute_indices(load_monthly(NC), scale=3)
    spei = idx["spei"]
    spei_cur = spei.sel(time=spei["time"].dt.year == CURRENT_YEAR).mean("time")  # (lat,lon)
    lats, lons = spei["latitude"].values, spei["longitude"].values
    rows, scored_cells = [], set()
    for i, la in enumerate(lats):
        for j, lo in enumerate(lons):
            v = float(spei_cur.values[i, j])
            if np.isnan(v):
                continue
            cell = h3.latlng_to_cell(float(la), float(lo), 8)
            scored_cells.add(cell)
            for scen in SCENARIO_WARMING_C:
                for horz in HORIZON_FRACTION:
                    sc = drought_score(v, scen, horz)
                    rows.append({"id": str(uuid.uuid4()), "h3": cell, "res": 8, "hz": "drought",
                                 "scen": scen, "horz": horz, "score": sc,
                                 "bucket": score_to_bucket(sc).value, "mv": MODEL_VERSION,
                                 "dv": vintage, "now": now})

    with get_session() as s:
        s.execute(text("UPDATE canonical_scores SET valid_to=:now WHERE hazard_type='drought' AND valid_to IS NULL"), {"now": now})
        for k in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario,
                    time_horizon, risk_score, risk_bucket, model_version, data_vintage, scored_at, valid_from, valid_to)
                VALUES (:id,:h3,:res,:hz,:scen,:horz,:score,:bucket,:mv,:dv,:now,:now,NULL)
            """), rows[k:k + 2000])

        # --- 3. coffee plots snapped onto scored drought cells ---
        cid = s.execute(text("SELECT commodity_id FROM sc_commodities WHERE name='Coffee'")).scalar()
        sup = s.execute(text("SELECT supplier_id FROM sc_suppliers WHERE org_id=:o AND commodity_id=:c"), {"o": ORG, "c": cid}).scalar()
        plots = []
        for name, lat, lon in PLOTS:
            glat, glon = round(lat * 10) / 10, round(lon * 10) / 10
            cell = h3.latlng_to_cell(glat, glon, 8)
            if cell not in scored_cells:
                cell = min(scored_cells, key=lambda c: (lambda p: (p[0]-lat)**2 + (p[1]-lon)**2)(h3.cell_to_latlng(c)))
            plots.append({"id": str(uuid.uuid4()), "o": ORG, "sup": str(sup), "c": str(cid),
                          "pn": name, "lat": lat, "lon": lon, "h3": cell, "cc": "BR",
                          "rg": name.rsplit(" ", 1)[0], "sp": round(22_000_000/len(PLOTS), 2),
                          "vs": round(1.0/len(PLOTS), 4), "now": now})
        s.execute(text("""
            INSERT INTO sc_sourcing_plots (plot_id, org_id, supplier_id, commodity_id, plot_name, latitude,
                longitude, h3_cell, country, region, annual_spend_eur, volume_share, eudr_status, eudr_geolocated_at)
            VALUES (:id,:o,:sup,:c,:pn,:lat,:lon,:h3,:cc,:rg,:sp,:vs,'compliant',:now)
        """), plots)

    with get_session() as s:
        s.execute(text("UPDATE model_registry SET is_active=false WHERE hazard_type='drought'"))
        s.execute(text("""
            INSERT INTO model_registry (model_id, hazard_type, model_version, algorithm, training_data_vintage, validation_note, is_active, created_at)
            VALUES (:id,'drought',:mv,'SPEI percentile Φ(−SPEI) vs 1991-2020',:dv,
                'Drought = validated coffee signal (2021 driest in 34, SPEI −0.86 → score 80.5). Warming shifts SPEI drier in scenarios. The Jul-2021 FROST (the other 2021 driver, season-min −3.46C -- see scripts/wire_frost_demo.py) is now also scored and compounds with drought on Coffee''s plots (COMPOUND_HAZARDS in supply_cogs.py) -- combined the chain reproduces +48.5% price move vs the real +44-60% observed, drought alone only reaches +33.6%.',
                true,:now)
            ON CONFLICT (model_version) DO UPDATE SET
                training_data_vintage = EXCLUDED.training_data_vintage,
                validation_note = EXCLUDED.validation_note,
                is_active = true, created_at = EXCLUDED.created_at
        """), {"id": str(uuid.uuid4()), "mv": MODEL_VERSION, "dv": vintage, "now": now})

    print(f"wired Coffee: scored {len(rows)} drought rows over {len(scored_cells)} Brazil cells, {len(PLOTS)} plots")
    with get_session() as s:
        for r in s.execute(text("""
            SELECT p.plot_name, ROUND(v.physical_risk_score::numeric,1) score
            FROM sc_sourcing_plots p JOIN v_sc_plot_physical_risk v ON v.plot_id=p.plot_id
            WHERE p.commodity_id=(SELECT commodity_id FROM sc_commodities WHERE name='Coffee')
              AND v.hazard_type='drought' AND v.scenario='baseline' AND v.time_horizon='current'
        """)).mappings().all():
            print(f"  {r['plot_name']}: drought {r['score']}")


if __name__ == "__main__":
    main()
