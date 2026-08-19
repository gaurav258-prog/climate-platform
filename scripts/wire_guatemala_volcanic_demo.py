"""
Wire a Guatemala coffee plot into the Terra Foods demo on the volcanic hazard.

Adds a sourcing plot in Alotenango (Antigua region, Sacatepéquez) — a real
coffee-growing municipality ~8km from Fuego's summit, already scored by
scripts/score_volcanic_event.py (hazard_type='volcanic'). Placed under the
EXISTING "Coffee" commodity (added by wire_coffee_demo.py for Brazil) rather
than a new commodity — sc_commodities.name is UNIQUE, so Coffee is one global
price/COGS line item across origins, same as Brazil + Vietnam would be.

KNOWN LIMITATION (see docs/VOLCANIC_HAZARD_METHODOLOGY.md): Coffee's calibrated
sensitivity (0.45) and global_share (0.35) were fit to Brazil's 2021 DROUGHT
event. Folding Guatemala's volcanic-ASHFALL hazard under the same commodity
means the live product blends two distinct origins/mechanisms under one
sensitivity/global_share — the schema has no per-plot or per-mechanism override.
This is disclosed, not silently absorbed: Guatemala's plot is added but "Coffee"
stays in BACKTESTED (Brazil's validation still holds); scripts/backtest_volcanic.py
separately reports what a properly origin-specific calculation implies for
Guatemala using its REAL (much smaller) world coffee share, alongside what the
current shared-commodity model actually produces.

Idempotent. Run: .venv/bin/python scripts/wire_guatemala_volcanic_demo.py
"""
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session

ORG = "33333333-3333-4333-8333-333333333333"
# Alotenango, Sacatepéquez -- a real Antigua-region coffee municipality ~8km
# from Fuego's summit; already scored by score_volcanic_event.py.
PLOT_NAME = "Alotenango (Antigua) coffee"
LAT, LON = 14.5083, -90.8167
SPEND_EUR = 3_500_000  # added ON TOP of Brazil's existing 22M -- Guatemala is the smaller origin here


def main():
    now = datetime.now(timezone.utc)
    cell = h3.latlng_to_cell(LAT, LON, 8)

    with get_session() as s:
        cid = s.execute(text("SELECT commodity_id FROM sc_commodities WHERE name='Coffee'")).scalar()
        if not cid:
            print("Coffee commodity not found -- run scripts/wire_coffee_demo.py first")
            return
        row = s.execute(text("""
            SELECT risk_score FROM canonical_scores
            WHERE hazard_type='volcanic' AND h3_cell=:h AND valid_to IS NULL
              AND scenario='baseline' AND time_horizon='current'
        """), {"h": cell}).first()
        if not row:
            print(f"cell {cell} has no volcanic score -- run scripts/score_volcanic_event.py first")
            return

        sup = s.execute(text("""
            SELECT supplier_id FROM sc_suppliers WHERE org_id=:o AND commodity_id=:c AND country='GT'
        """), {"o": ORG, "c": cid}).scalar()
        if not sup:
            sup = s.execute(text("""
                INSERT INTO sc_suppliers (supplier_id, org_id, name, commodity_id, tier, country)
                VALUES (:id,:o,'Antigua Highland Co-op',:c,1,'GT') RETURNING supplier_id
            """), {"id": str(uuid.uuid4()), "o": ORG, "c": cid}).scalar()

        # idempotent: clear any prior Guatemala coffee plot before re-inserting
        s.execute(text("DELETE FROM sc_sourcing_plots WHERE org_id=:o AND commodity_id=:c AND country='GT'"),
                  {"o": ORG, "c": cid})

        # bump the Coffee BOM line's spend to include Guatemala on top of Brazil's existing 22M
        pid = s.execute(text("""
            SELECT product_id FROM sc_products WHERE org_id=:o AND name='Cold Brew Coffee 1L'
        """), {"o": ORG}).scalar()
        s.execute(text("""
            UPDATE sc_bom_lines SET annual_spend_eur = annual_spend_eur + :add
            WHERE product_id=:p AND commodity_id=:c
        """), {"add": SPEND_EUR, "p": pid, "c": cid})

        s.execute(text("""
            INSERT INTO sc_sourcing_plots
                (plot_id, org_id, supplier_id, commodity_id, plot_name, latitude, longitude, h3_cell,
                 country, region, annual_spend_eur, volume_share, eudr_status, eudr_geolocated_at)
            VALUES (:id,:o,:sup,:c,:pn,:lat,:lon,:h3,'GT','Antigua (Sacatepéquez)',:sp,0.15,'compliant',:now)
        """), {"id": str(uuid.uuid4()), "o": ORG, "sup": str(sup), "c": str(cid), "pn": PLOT_NAME,
               "lat": LAT, "lon": LON, "h3": cell, "sp": SPEND_EUR, "now": now})

    print(f"wired Guatemala coffee: {PLOT_NAME} @ ({LAT},{LON}), cell {cell}, "
          f"volcanic score {row[0]}, spend €{SPEND_EUR/1e6:.1f}m")


if __name__ == "__main__":
    main()
