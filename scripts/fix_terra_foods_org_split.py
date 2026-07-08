"""
One-time cleanup: detach Terra Foods' demo data from Stellar Logistics REIT's
org_id (33333333-...), which scripts/seed_demo_supply.py mistakenly reused
instead of Terra Foods' own dedicated org_id. Every time either seed script ran,
it fought the other over that same organizations row (renaming it back and
forth between "Stellar Logistics REIT" and "Terra Foods", type 'reit' vs
'manufacturer') -- and it meant Terra Foods had no reachable catalog entry of
its own, since 'reit' maps to the realestate industry, not agriculture.

Deletes the sc_* rows, entitlements, and demo user that were seeded under
Stellar's org_id by the old buggy script. Run BEFORE re-running
seed_demo_supply.py (which will reseed everything under Terra Foods' own
org_id) and seed_auth_demo.py (which restores Stellar's org row).

Idempotent -- safe to re-run; a clean install with no stray rows is a no-op.

Run:  .venv/bin/python scripts/fix_terra_foods_org_split.py
"""
from sqlalchemy import text

from core.db.session import get_session

STELLAR = "33333333-3333-4333-8333-333333333333"


def main():
    with get_session() as s:
        n_bom = s.execute(text("""
            DELETE FROM sc_bom_lines
            WHERE product_id IN (SELECT product_id FROM sc_products WHERE org_id=:o)
        """), {"o": STELLAR}).rowcount
        n_plots = s.execute(text("DELETE FROM sc_sourcing_plots WHERE org_id=:o"), {"o": STELLAR}).rowcount
        n_sup = s.execute(text("DELETE FROM sc_suppliers WHERE org_id=:o"), {"o": STELLAR}).rowcount
        n_prod = s.execute(text("DELETE FROM sc_products WHERE org_id=:o"), {"o": STELLAR}).rowcount
        n_ent = s.execute(text("""
            DELETE FROM org_entitlements WHERE org_id=:o AND offering_id IN ('supply-chain','trust')
        """), {"o": STELLAR}).rowcount
        n_user = s.execute(text("DELETE FROM users WHERE org_id=:o AND email='analyst@terra.demo'"),
                            {"o": STELLAR}).rowcount
        print(f"cleaned Stellar org ({STELLAR}): {n_plots} sourcing plots, {n_bom} BOM lines, "
              f"{n_sup} suppliers, {n_prod} products, {n_ent} stray entitlements, {n_user} stray users")
        print("next: re-run seed_auth_demo.py (restores Stellar's org row) "
              "then seed_demo_supply.py (reseeds Terra Foods under its own org_id)")


if __name__ == "__main__":
    main()
