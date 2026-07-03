"""
Wire a Puerto Rico coffee plot into the Terra Foods demo on the storm hazard.

Adds a sourcing plot in Adjuntas — a real coffee-growing municipality in Puerto
Rico's central mountain coffee belt, ~29km from Hurricane Maria's track and already
scored by scripts/score_storm_event.py (hazard_type='storm'). Placed under the
EXISTING "Coffee" commodity (added by wire_coffee_demo.py for Brazil, extended by
wire_guatemala_volcanic_demo.py for Guatemala) rather than a new commodity —
sc_commodities.name is UNIQUE, so Coffee is one global price/COGS line item across
origins.

KNOWN LIMITATION (see docs/STORM_HAZARD_METHODOLOGY.md, same one Guatemala's volcanic
plot already carries): Coffee's calibrated sensitivity (0.45) and global_share (0.35)
were fit to Brazil's 2021 DROUGHT event. Folding Puerto Rico's storm hazard under the
same commodity means the live product blends a third origin/mechanism under one
sensitivity/global_share — disclosed, not resolved. Puerto Rico stays 'indicative',
not added to BACKTESTED, same as Guatemala.

Idempotent. Run: .venv/bin/python scripts/wire_puerto_rico_storm_demo.py
"""
from datetime import datetime, timezone

import h3
import uuid
from sqlalchemy import text

from core.db.session import get_session

ORG = "33333333-3333-4333-8333-333333333333"
# Adjuntas, Puerto Rico -- a real coffee-growing municipality in the central mountain
# coffee belt, ~29km from Hurricane Maria's track; already scored by score_storm_event.py.
PLOT_NAME = "Adjuntas coffee"
LAT, LON = 18.1630, -66.7220
SPEND_EUR = 2_800_000  # added ON TOP of Brazil's 22M + Guatemala's 3.5M -- the smallest origin here


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
            WHERE hazard_type='storm' AND h3_cell=:h AND valid_to IS NULL
              AND scenario='baseline' AND time_horizon='current'
        """), {"h": cell}).first()
        if not row:
            print(f"cell {cell} has no storm score -- run scripts/score_storm_event.py first")
            return

        sup = s.execute(text("""
            SELECT supplier_id FROM sc_suppliers WHERE org_id=:o AND commodity_id=:c AND country='PR'
        """), {"o": ORG, "c": cid}).scalar()
        if not sup:
            sup = s.execute(text("""
                INSERT INTO sc_suppliers (supplier_id, org_id, name, commodity_id, tier, country)
                VALUES (:id,:o,'Cordillera Central Co-op',:c,1,'PR') RETURNING supplier_id
            """), {"id": str(uuid.uuid4()), "o": ORG, "c": cid}).scalar()

        s.execute(text("DELETE FROM sc_sourcing_plots WHERE org_id=:o AND commodity_id=:c AND country='PR'"),
                  {"o": ORG, "c": cid})

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
            VALUES (:id,:o,:sup,:c,:pn,:lat,:lon,:h3,'PR','Cordillera Central',:sp,0.10,'compliant',:now)
        """), {"id": str(uuid.uuid4()), "o": ORG, "sup": str(sup), "c": str(cid), "pn": PLOT_NAME,
               "lat": LAT, "lon": LON, "h3": cell, "sp": SPEND_EUR, "now": now})

    print(f"wired Puerto Rico coffee: {PLOT_NAME} @ ({LAT},{LON}), cell {cell}, "
          f"storm score {row[0]}, spend €{SPEND_EUR/1e6:.1f}m")


if __name__ == "__main__":
    main()
