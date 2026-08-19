"""
Seed a demo food-manufacturer procurement book into the sc_* tables.

"Terra Foods (demo)" — a European CPG, org type 'manufacturer' (maps to the
'agriculture' catalog industry). SKUs → bill of materials → commodities →
suppliers → sourcing plots. Plots are placed in cells that ARE already scored
(Iberia wildfire, Valencia flood) so COGS-at-risk is REAL, plus a cocoa plot in
West Africa that is intentionally UNSCORED — it demonstrates the governance rule
(exposure mapped, € pending drought/heat validation). Idempotent: clears the org.

Runs under its OWN dedicated org_id (55555555-...) -- this used to reuse
Stellar Logistics REIT's org_id (33333333-...) by mistake, which meant running
this script silently renamed/retyped the real-estate demo org and fought with
seed_auth_demo.py over the same row every time either script ran. Fixed by
giving Terra Foods its own org; see scripts/fix_terra_foods_org_split.py for
the one-time cleanup that detached the old data from Stellar.

Demo logins: admin@terra.demo / Demo!admin1, analyst@terra.demo / Demo!analyst1

Run:  .venv/bin/python scripts/seed_demo_supply.py
"""
import uuid

import h3
from sqlalchemy import text

from api.security import hash_password
from core.db.session import get_session
from services.ingestion.regions import get_region

ORG = "55555555-5555-4555-8555-555555555555"

# name, hs, eudr_covered, demand_elasticity (neg), primary_hazards, share note
COMMODITIES = [
    ("Olive oil",   "1509", False, -0.20, "wildfire,drought,heat_acute", "Spain ~45% of world olive oil"),
    ("Citrus",      "0805", False, -0.30, "flood,heat_acute",            "Mediterranean basin"),
    ("Almonds",     "0802", False, -0.35, "wildfire,drought",            "California + Spain"),
    ("Durum wheat", "1001", False, -0.25, "heat_acute,drought",          "Global; Med. durum belt"),
    ("Wine grapes", "0806", False, -0.40, "wildfire,heat_acute",         "Mediterranean"),
    # Sugar beet, NOT cane: Spain grows no commercial sugar cane (cane is Brazil/India/
    # Thailand). Spain's real sugar crop is beet, in Castilla y Leon — a dry continental
    # crop whose risks are drought/heat, not flood. This book previously carried "Cane
    # sugar" plots sitting in Valencia, which is citrus country: a fabricated geography.
    ("Sugar beet",  "1212", False, -0.20, "drought,heat_acute",          "EU beet ~20% of world sugar; Spain a small share"),
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
    "Valencia Orange Juice 1L":               [("Citrus", 62, 27_000_000), ("Sugar beet", 10, 4_400_000)],
    "Almond & Honey Snack Bar":               [("Almonds", 48, 18_700_000), ("Sugar beet", 14, 5_500_000)],
    "Artisan Dark Chocolate 100g":            [("Cocoa", 52, 30_000_000), ("Sugar beet", 18, 10_400_000)],
    "Durum Pasta 500g":                       [("Durum wheat", 60, 22_800_000)],
    "Sparkling Grape Refresher 750ml":        [("Wine grapes", 45, 12_150_000), ("Sugar beet", 12, 3_240_000)],
}

# commodity → list of (region, country, [candidate boxes] or fixed coords, eudr_status)
# EU commodities are placed in scored cells (queried below); cocoa is fixed & unscored.
# commodity -> (region label, country, hazard to place against, region_key in
# services/ingestion/regions.py). The region_key is load-bearing, not decoration: a plot is
# only ever placed in a scored cell that actually falls INSIDE that region's bounds.
#
# This used to take "the highest-scoring cell for this hazard, anywhere" and then staple a
# hardcoded label on it — so "Valencia Cane sugar plot 3" sat at (39.99, -0.0006), which is
# not Valencia, and nothing tied a plot's stated geography to its coordinates. A plot whose
# label disagrees with its location is a fabricated plot.
EU_PLACEMENTS = {
    "Olive oil":   ("Andalusia",       "ES", "wildfire", "spain_olive"),
    "Almonds":     ("Alentejo",        "PT", "wildfire", "portugal_alentejo"),
    "Wine grapes": ("Extremadura",     "ES", "wildfire", "spain_extremadura"),
    "Durum wheat": ("Andalusia",       "ES", "wildfire", "spain_olive"),
    "Citrus":      ("Valencia",        "ES", "flood",    "spain_citrus"),
}

# Crops placed at FIXED, REAL coordinates rather than "wherever this hazard is scored".
# Used where the true growing area has no scored cell yet: we still put the plot where the
# crop actually grows and let the publish gate withhold its € (exposure mapped, € pending)
# — the one thing we never do is move the plot somewhere convenient to make a number appear.
#   commodity -> [(place, country, lat, lon)]
FIXED_PLOTS = {
    # West-Africa cocoa belt.
    "Cocoa": [
        ("Ashanti (Ghana)", "GH", 6.75, -1.62),
        ("Sud-Comoé (Côte d'Ivoire)", "CI", 6.10, -3.20),
    ],
    # Castilla y Leon — Spain's real sugar-BEET belt. Spain grows no commercial cane; these
    # plots previously sat in Valencia (citrus country) labelled "Cane sugar". Drought is not
    # yet scored here, so beet is honestly exposure-mapped with its euro withheld.
    "Sugar beet": [
        ("Valladolid", "ES", 41.65, -4.72),
        ("Palencia",   "ES", 42.01, -4.53),
        ("Zamora",     "ES", 41.50, -5.75),
    ],
}


def scored_cells(session, hazard, region_key, n=400):
    """Cells scored across ALL scenarios × horizons (present at both baseline/current AND
    hot_house/2100, so a plot's risk responds to the scenario selector) AND lying inside
    `region_key`'s real bounds — a plot must sit where its label says it sits.

    Standing lane only: a nowcast ("is it hot today") must never be what a demo plot is
    placed on, same rule the crop engine follows (see migration score_lane_20260715)."""
    rows = session.execute(text("""
        SELECT h3_cell FROM canonical_scores
        WHERE hazard_type=:h AND valid_to IS NULL AND score_lane='standing'
          AND scenario='baseline' AND time_horizon='current'
          AND h3_cell IN (SELECT h3_cell FROM canonical_scores
                          WHERE valid_to IS NULL AND score_lane='standing'
                            AND scenario='hot_house_3_5c' AND time_horizon='2100')
        ORDER BY risk_score DESC
    """), {"h": hazard}).scalars().all()

    r = get_region(region_key)
    inside = []
    for cell in rows:
        lat, lon = h3.cell_to_latlng(cell)
        if r.min_lat <= lat <= r.max_lat and r.min_lon <= lon <= r.max_lon:
            inside.append(cell)
            if len(inside) >= n:
                break
    return inside


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
                   "cc": {"Cocoa": "GH", "Almonds": "PT"}.get(cname, "ES")}).scalar()
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

        # sourcing plots — each EU commodity in scored cells INSIDE ITS OWN REGION; cocoa unscored
        plots = []
        for cname, (region, country, hazard, region_key) in EU_PLACEMENTS.items():
            total = commodity_spend.get(cname, 0)
            n_plots = 3
            pool = scored_cells(s, hazard, region_key, n_plots)
            if len(pool) < n_plots:
                # Never silently place the plot somewhere else to make the demo look full.
                # No scored cell in the real region = the honest answer is fewer plots, and the
                # gate then withholds that commodity's € (exposure mapped, € pending).
                print(f"  ! {cname}: only {len(pool)} scored '{hazard}' cells inside "
                      f"{region_key} — placing {len(pool)} plot(s), not {n_plots}")
            for i, cell in enumerate(pool):
                lat, lon = h3.cell_to_latlng(cell)
                # split across the plots we ACTUALLY placed, so the commodity's spend still
                # reconciles when a region yields fewer scored cells than we hoped for
                vshare = round(1.0 / len(pool), 4)
                plots.append({
                    "id": str(uuid.uuid4()), "o": ORG, "sup": sup[cname], "c": cid[cname],
                    "pn": f"{region} {cname} plot {i+1}", "lat": round(lat, 5), "lon": round(lon, 5),
                    "h3": cell, "cc": country, "rg": region,
                    "sp": round(total * vshare, 2), "vs": vshare,
                    "eudr": "compliant", "geo": True,
                })
        # crops at fixed REAL coordinates (cocoa belt, Castilla y Leon beet). Scored or not is
        # the golden source's business — we place them where they actually grow.
        for cname, placements in FIXED_PLOTS.items():
            total = commodity_spend.get(cname, 0)
            vs = round(1.0 / len(placements), 4)
            for name, country, lat, lon in placements:
                cell = h3.latlng_to_cell(lat, lon, 8)
                plots.append({
                    "id": str(uuid.uuid4()), "o": ORG, "sup": sup[cname], "c": cid[cname],
                    "pn": f"{name} {cname.lower()} plot", "lat": lat, "lon": lon, "h3": cell,
                    "cc": country, "rg": name,
                    "sp": round(total * vs, 2), "vs": vs,
                    "eudr": "compliant", "geo": True,
                })
        s.execute(text("""
            INSERT INTO sc_sourcing_plots
                (plot_id, org_id, supplier_id, commodity_id, plot_name, latitude, longitude, h3_cell,
                 country, region, annual_spend_eur, volume_share, eudr_status, eudr_geolocated_at)
            VALUES (:id,:o,:sup,:c,:pn,:lat,:lon,:h3,:cc,:rg,:sp,:vs,:eudr, CASE WHEN :geo THEN now() ELSE NULL END)
        """), plots)

        # demo users for the tenant (login → agriculture workspace) -- an admin + an
        # analyst, matching the admin/analyst pattern every other demo org already has.
        ROLE_PERMS = {
            "admin": [
                "modules.view", "reports.view", "reports.publish", "pricing.view", "pricing.approve",
                "admin.users.manage", "admin.roles.manage", "admin.audit.view", "admin.approval_policy.manage",
                "approvals.create", "approvals.view", "approvals.decide", "portal.use", "supply.locations.write",
            ],
            # analyst is a MAKER: can add/edit/delete locations, but material changes go to a checker
            "analyst": ["modules.view", "reports.view", "pricing.view", "approvals.create", "portal.use", "supply.locations.write"],
            # approver is a CHECKER: clears 4-eyes requests (must differ from the maker)
            "approver": ["modules.view", "reports.view", "approvals.view", "approvals.decide", "portal.use", "supply.locations.write"],
        }
        for email, full_name, pw, role_name in [
            ("admin@terra.demo",    "Teo Admin (Terra)",     "Demo!admin1",   "admin"),
            ("analyst@terra.demo",  "Tomas Analyst (Terra)", "Demo!analyst1", "analyst"),
            ("approver@terra.demo", "Pia Approver (Terra)",  "Demo!approve1", "approver"),
        ]:
            s.execute(text("DELETE FROM users WHERE org_id=:o AND email=:e"), {"o": ORG, "e": email})
            uid = str(uuid.uuid4())
            s.execute(text("""
                INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status)
                VALUES (:u,:o,:e,:r,:fn,:pw,'active')
            """), {"u": uid, "o": ORG, "e": email, "r": role_name, "fn": full_name, "pw": hash_password(pw)})

            # grant the role if it exists for this org already; else clone it fresh
            role = s.execute(text("SELECT role_id FROM roles WHERE org_id=:o AND name=:n"),
                              {"o": ORG, "n": role_name}).scalar()
            if not role:
                role = str(uuid.uuid4())
                s.execute(text("INSERT INTO roles (role_id, org_id, name, description) VALUES (:r,:o,:n,:d)"),
                          {"r": role, "o": ORG, "n": role_name, "d": f"{role_name} role"})
                s.execute(text("""
                    INSERT INTO role_permissions (role_id, permission_id)
                    SELECT :r, permission_id FROM permissions WHERE code = ANY(:codes)
                """), {"r": role, "codes": ROLE_PERMS[role_name]})
            s.execute(text("INSERT INTO user_roles (user_id, role_id) VALUES (:u,:r) ON CONFLICT DO NOTHING"),
                      {"u": uid, "r": str(role)})

    # Snap plots onto the scored grid for each crop's CALIBRATED DRIVER hazard. This is part of
    # seeding, not an afterthought: our climatologies are computed on a sampled grid, so a plot's
    # own res-8 cell often isn't scored and its driver reads as absent — the gate then withholds
    # the crop's €. This used to be a hardcoded plot list inside score_cocoa_heat.py, so every
    # re-seed silently UN-snapped Ghana (half the cocoa spend, ~15% of world cocoa) and nothing
    # noticed. Any script that (re)creates plots must snap them.
    import os
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from snap_plots_to_scored_grid import main as snap
    print("\nsnapping plots onto the scored grid (per crop's calibrated driver hazard):")
    snap(argv=[])

    with get_session() as s:
        # report
        np = s.execute(text("SELECT count(*) FROM sc_sourcing_plots WHERE org_id=:o"), {"o": ORG}).scalar()
        scored = s.execute(text("""
            SELECT count(DISTINCT plot_id) FROM v_sc_plot_physical_risk WHERE org_id=:o
        """), {"o": ORG}).scalar()
        spend = sum(commodity_spend.values())
        print(f"seeded Terra Foods: {len(PRODUCTS)} SKUs, {len(cid)} commodities, {np} plots, ingredient spend €{spend/1e6:.0f}m")
        print(f"{scored} of {np} plots fall in scored cells (cocoa plots = no_canonical_score, € pending)")
        print("demo login: admin@terra.demo / Demo!admin1  (or analyst@terra.demo / Demo!analyst1)")


if __name__ == "__main__":
    main()
