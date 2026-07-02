"""
Seed a demo food-manufacturer procurement book into the sc_* tables.

"Terra Foods (demo)" — a European CPG. SKUs → bill of materials → commodities →
suppliers → sourcing plots. Plots are placed in cells that ARE already scored
(Iberia wildfire, Valencia flood) so COGS-at-risk is REAL, plus a cocoa plot in
West Africa that is intentionally UNSCORED — it demonstrates the governance rule
(exposure mapped, € pending drought/heat validation). Idempotent: clears the org.

Run:  .venv/bin/python scripts/seed_demo_supply.py
"""
import uuid

import h3
from sqlalchemy import text

from core.db.session import get_session
from api.security import hash_password

ORG = "33333333-3333-4333-8333-333333333333"

# name, hs, eudr_covered, demand_elasticity (neg), primary_hazards, share note
COMMODITIES = [
    ("Olive oil",   "1509", False, -0.20, "wildfire,drought,heat_acute", "Spain ~45% of world olive oil"),
    ("Citrus",      "0805", False, -0.30, "flood,heat_acute",            "Mediterranean basin"),
    ("Almonds",     "0802", False, -0.35, "wildfire,drought",            "California + Spain"),
    ("Durum wheat", "1001", False, -0.25, "heat_acute,drought",          "Global; Med. durum belt"),
    ("Wine grapes", "0806", False, -0.40, "wildfire,heat_acute",         "Mediterranean"),
    ("Cane sugar",  "1701", False, -0.20, "flood,heat_acute",            "Global"),
    ("Cocoa",       "1801", True,  -0.20, "heat_acute,drought",          "Ghana+CIV ~60% of world cocoa"),
]

# sku, category, annual_units, revenue_eur, cogs_eur
PRODUCTS = [
    ("Mediterranean Olive-Oil Dressing 500ml", "Condiments",  22_000_000, 88_000_000, 55_000_000),
    ("Valencia Orange Juice 1L",               "Beverages",   30_000_000, 66_000_000, 44_000_000),
    ("Almond & Honey Snack Bar",               "Snacks",      40_000_000, 60_000_000, 39_000_000),
    ("Artisan Dark Chocolate 100g",            "Confectionery",35_000_000, 84_000_000, 58_000_000),
    ("Durum Pasta 500g",                       "Ambient",     50_000_000, 55_000_000, 38_000_000),
    ("Sparkling Grape Refresher 750ml",        "Beverages",   18_000_000, 40_000_000, 27_000_000),
]

# product name → [(commodity name, cost_share_pct, annual_spend_eur)]
BOM = {
    "Mediterranean Olive-Oil Dressing 500ml": [("Olive oil", 55, 30_000_000), ("Citrus", 8, 4_400_000)],
    "Valencia Orange Juice 1L":               [("Citrus", 62, 27_000_000), ("Cane sugar", 10, 4_400_000)],
    "Almond & Honey Snack Bar":               [("Almonds", 48, 18_700_000), ("Cane sugar", 14, 5_500_000)],
    "Artisan Dark Chocolate 100g":            [("Cocoa", 52, 30_000_000), ("Cane sugar", 18, 10_400_000)],
    "Durum Pasta 500g":                       [("Durum wheat", 60, 22_800_000)],
    "Sparkling Grape Refresher 750ml":        [("Wine grapes", 45, 12_150_000), ("Cane sugar", 12, 3_240_000)],
}

# commodity → list of (region, country, [candidate boxes] or fixed coords, eudr_status)
# EU commodities are placed in scored cells (queried below); cocoa is fixed & unscored.
EU_PLACEMENTS = {
    "Olive oil":   ("Andalusia",   "ES", "wildfire"),
    "Almonds":     ("Alentejo",    "PT", "wildfire"),
    "Wine grapes": ("Extremadura", "ES", "wildfire"),
    "Durum wheat": ("Andalusia",   "ES", "wildfire"),
    "Citrus":      ("Valencia",    "ES", "flood"),
    "Cane sugar":  ("Valencia",    "ES", "flood"),
}
COCOA_PLOTS = [
    ("Ashanti (Ghana)", "GH", 6.75, -1.62),
    ("Sud-Comoé (Côte d'Ivoire)", "CI", 6.10, -3.20),
]


def scored_cells(session, hazard, n=400):
    """Cells that are scored across ALL scenarios × horizons (present at both
    baseline/current AND hot_house/2100), so a plot's risk responds to the scenario
    selector. Otherwise a plot would drop to 'pending' under future scenarios."""
    rows = session.execute(text("""
        SELECT h3_cell FROM canonical_scores
        WHERE hazard_type=:h AND valid_to IS NULL AND scenario='baseline' AND time_horizon='current'
          AND h3_cell IN (SELECT h3_cell FROM canonical_scores
                          WHERE valid_to IS NULL AND scenario='hot_house_3_5c' AND time_horizon='2100')
        ORDER BY risk_score DESC LIMIT :n
    """), {"h": hazard, "n": n}).scalars().all()
    return list(rows)


def main():
    with get_session() as s:
        # org + entitlement + a demo user (tenant login)
        s.execute(text("""
            INSERT INTO organizations (org_id, name, type, country, aum_eur, employees, created_at, updated_at)
            VALUES (:o, 'Terra Foods (demo)', 'manufacturer', 'ES', 0, 7800, now(), now())
            ON CONFLICT (org_id) DO UPDATE SET name=EXCLUDED.name, type=EXCLUDED.type
        """), {"o": ORG})
        # clear prior demo graph for idempotency
        for t in ["sc_bom_lines", "sc_sourcing_plots", "sc_suppliers", "sc_products"]:
            s.execute(text(f"DELETE FROM {t} WHERE {'product_id IN (SELECT product_id FROM sc_products WHERE org_id=:o)' if t=='sc_bom_lines' else 'org_id=:o'}"), {"o": ORG})
        s.execute(text("""
            INSERT INTO org_entitlements (org_id, offering_id, enabled)
            VALUES (:o,'supply-chain',true),(:o,'trust',true)
            ON CONFLICT (org_id, offering_id) DO NOTHING
        """), {"o": ORG})

        # commodities (global; upsert)
        cid = {}
        for name, hs, eudr, elast, haz, note in COMMODITIES:
            row = s.execute(text("""
                INSERT INTO sc_commodities (name, hs_code, eudr_covered, demand_elasticity, primary_hazards, global_share_note)
                VALUES (:n,:hs,:e,:el,:hz,:note)
                ON CONFLICT (name) DO UPDATE SET demand_elasticity=EXCLUDED.demand_elasticity,
                    eudr_covered=EXCLUDED.eudr_covered, primary_hazards=EXCLUDED.primary_hazards,
                    global_share_note=EXCLUDED.global_share_note
                RETURNING commodity_id
            """), {"n": name, "hs": hs, "e": eudr, "el": elast, "hz": haz, "note": note}).scalar()
            cid[name] = str(row)

        # products
        pid = {}
        for name, cat, units, rev, cogs in PRODUCTS:
            row = s.execute(text("""
                INSERT INTO sc_products (product_id, org_id, name, category, annual_units, annual_revenue_eur, annual_cogs_eur)
                VALUES (:id,:o,:n,:c,:u,:r,:g) RETURNING product_id
            """), {"id": str(uuid.uuid4()), "o": ORG, "n": name, "c": cat, "u": units, "r": rev, "g": cogs}).scalar()
            pid[name] = str(row)

        # suppliers (one per commodity) + BOM
        sup = {}
        for cname in cid:
            row = s.execute(text("""
                INSERT INTO sc_suppliers (supplier_id, org_id, name, commodity_id, tier, country)
                VALUES (:id,:o,:n,:c,1,:cc) RETURNING supplier_id
            """), {"id": str(uuid.uuid4()), "o": ORG, "n": f"{cname} Co-op", "c": cid[cname],
                   "cc": "GH" if cname == "Cocoa" else "ES"}).scalar()
            sup[cname] = str(row)

        commodity_spend = {}
        for pname, lines in BOM.items():
            for cname, share, spend in lines:
                s.execute(text("""
                    INSERT INTO sc_bom_lines (product_id, commodity_id, cost_share_pct, annual_spend_eur)
                    VALUES (:p,:c,:s,:sp)
                    ON CONFLICT (product_id, commodity_id) DO UPDATE SET cost_share_pct=EXCLUDED.cost_share_pct,
                        annual_spend_eur=EXCLUDED.annual_spend_eur
                """), {"p": pid[pname], "c": cid[cname], "s": share, "sp": spend})
                commodity_spend[cname] = commodity_spend.get(cname, 0) + spend

        # sourcing plots — EU commodities in real scored cells; cocoa unscored
        wildfire = scored_cells(s, "wildfire", 400)
        flood = scored_cells(s, "flood", 200)
        plots = []
        pick = {"wildfire": iter(wildfire), "flood": iter(flood)}
        for cname, (region, country, hazard) in EU_PLACEMENTS.items():
            total = commodity_spend.get(cname, 0)
            n_plots = 3
            for i in range(n_plots):
                cell = next(pick[hazard])
                lat, lon = h3.cell_to_latlng(cell)
                vshare = round(1.0 / n_plots, 4)
                plots.append({
                    "id": str(uuid.uuid4()), "o": ORG, "sup": sup[cname], "c": cid[cname],
                    "pn": f"{region} {cname} plot {i+1}", "lat": round(lat, 5), "lon": round(lon, 5),
                    "h3": cell, "cc": country, "rg": region,
                    "sp": round(total * vshare, 2), "vs": vshare,
                    "eudr": "compliant", "geo": True,
                })
        # cocoa — West Africa, UNSCORED (no canonical_scores cell) → € pending
        total_cocoa = commodity_spend.get("Cocoa", 0)
        for name, country, lat, lon in COCOA_PLOTS:
            cell = h3.latlng_to_cell(lat, lon, 8)
            plots.append({
                "id": str(uuid.uuid4()), "o": ORG, "sup": sup["Cocoa"], "c": cid["Cocoa"],
                "pn": f"{name} cocoa plot", "lat": lat, "lon": lon, "h3": cell, "cc": country,
                "rg": name, "sp": round(total_cocoa / len(COCOA_PLOTS), 2), "vs": round(1.0/len(COCOA_PLOTS), 4),
                "eudr": "compliant", "geo": True,
            })
        s.execute(text("""
            INSERT INTO sc_sourcing_plots
                (plot_id, org_id, supplier_id, commodity_id, plot_name, latitude, longitude, h3_cell,
                 country, region, annual_spend_eur, volume_share, eudr_status, eudr_geolocated_at)
            VALUES (:id,:o,:sup,:c,:pn,:lat,:lon,:h3,:cc,:rg,:sp,:vs,:eudr, CASE WHEN :geo THEN now() ELSE NULL END)
        """), plots)

        # demo user for the tenant (login → agriculture workspace)
        s.execute(text("DELETE FROM users WHERE org_id=:o AND email='analyst@terra.demo'"), {"o": ORG})
        uid = str(uuid.uuid4())
        s.execute(text("""
            INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status)
            VALUES (:u,:o,'analyst@terra.demo','analyst','Tomas Analyst (Terra)',:pw,'active')
        """), {"u": uid, "o": ORG, "pw": hash_password("Demo!analyst1")})
        # grant analyst role if it exists for this org (seeded by seed_auth_demo per-org); else skip
        role = s.execute(text("SELECT role_id FROM roles WHERE org_id=:o AND name='analyst'"), {"o": ORG}).scalar()
        if not role:
            # clone a global/other analyst role's permissions into a new org role
            role = str(uuid.uuid4())
            s.execute(text("INSERT INTO roles (role_id, org_id, name, description) VALUES (:r,:o,'analyst','Analyst')"),
                      {"r": role, "o": ORG})
            s.execute(text("""
                INSERT INTO role_permissions (role_id, permission_id)
                SELECT :r, permission_id FROM permissions
                WHERE code IN ('modules.view','reports.view','pricing.view','portal.use','approvals.create')
            """), {"r": role})
        s.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u,:r) ON CONFLICT DO NOTHING"),
                  {"u": uid, "r": str(role)})

        # report
        np = s.execute(text("SELECT count(*) FROM sc_sourcing_plots WHERE org_id=:o"), {"o": ORG}).scalar()
        scored = s.execute(text("""
            SELECT count(DISTINCT plot_id) FROM v_sc_plot_physical_risk WHERE org_id=:o
        """), {"o": ORG}).scalar()
        spend = sum(commodity_spend.values())
        print(f"seeded Terra Foods: {len(PRODUCTS)} SKUs, {len(cid)} commodities, {np} plots, ingredient spend €{spend/1e6:.0f}m")
        print(f"{scored} of {np} plots fall in scored cells (cocoa plots = no_canonical_score, € pending)")
        print("demo login: analyst@terra.demo / Demo!analyst1")


if __name__ == "__main__":
    main()
