"""Seed a realistic demo asset-manager book on the new holdings foundation
(migration f8a9b0c1d2e3), to prove the footprint model end-to-end against the
REAL golden source — no fabricated scores.

The demonstration case is the exact failure mode of the old single-point model:
an issuer whose HQ sits in a low-hazard cell but whose PRODUCTION PLANTS (the
bulk of its materiality) sit in high-flood cells. The old "one lat/lon = HQ"
model scores it safe; the footprint model scores it High because the plants
dominate the materiality-weighted roll-up.

Facilities are placed in h3 cells that are ACTUALLY scored in canonical_scores
(verified at seed time), so issuer_physical_scores() joins to live data.

Idempotent: wipes and re-inserts the demo fund/issuers for the asset-manager org.
Run: .venv/bin/python scripts/seed_demo_asset_manager.py
"""
import h3
from sqlalchemy import text

from core.db.session import get_session

ASSET_MGR_ORG = "44444444-4444-4444-8444-444444444444"  # Nordkap Asset Management (demo)

# Real high-flood cells (verified > 65 in canonical_scores) + real low-flood cells (< 10).
HIGH_FLOOD_CELLS = ["883954caa5fffff", "8839545867fffff", "883954cb09fffff", "883954b55bfffff"]
LOW_FLOOD_CELLS = ["883950c82dfffff", "8839560033fffff", "883956014dfffff"]


def latlon(cell):
    lat, lon = h3.cell_to_latlng(cell)
    return round(lat, 5), round(lon, 5)


# (name, issuer_type, country, sector, nace, asset_class, isin,
#  facilities: [(name, type, cell, weight, basis)])
ISSUERS = [
    # THE demonstration issuer: HQ safe, plants exposed. Footprint model must
    # score this High even though its HQ cell is low-flood.
    ("Iberia Foods SA", "corporate", "ES", "Food manufacturing", "10.89", "equity", "ES00FOODS001", [
        ("Madrid HQ", "hq", LOW_FLOOD_CELLS[0], 0.10, "revenue"),
        ("Valencia Plant 1", "plant", HIGH_FLOOD_CELLS[0], 0.35, "revenue"),
        ("Valencia Plant 2", "plant", HIGH_FLOOD_CELLS[1], 0.30, "revenue"),
        ("Valencia Warehouse", "warehouse", HIGH_FLOOD_CELLS[2], 0.25, "revenue"),
    ]),
    # A genuinely low-risk issuer: whole footprint in safe cells.
    ("Nordic Software AB", "corporate", "SE", "Software", "62.01", "equity", "SE00SOFT0001", [
        ("Stockholm HQ", "hq", LOW_FLOOD_CELLS[1], 0.60, "revenue"),
        ("Malmo Office", "office", LOW_FLOOD_CELLS[2], 0.40, "revenue"),
    ]),
    # A partially-covered issuer: only some facilities land in scored cells, to
    # exercise the scored_weight_pct disclosure (never impute the unscored ones).
    ("Global Logistics NV", "corporate", "NL", "Logistics", "52.10", "corporate_bond", "NL00LOGIS001", [
        ("Rotterdam Hub", "warehouse", HIGH_FLOOD_CELLS[3], 0.50, "assets"),
        ("Unscored Depot", "warehouse", "8801234567fffff", 0.50, "assets"),  # deliberately not in canonical_scores
    ]),
]


def main():
    with get_session() as s:
        # verify the chosen cells are really scored (fail loudly rather than seed a lie)
        scored = set(s.execute(text("""
            SELECT DISTINCT h3_cell FROM canonical_scores
            WHERE hazard_type='flood' AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
              AND h3_cell = ANY(:cells)
        """), {"cells": HIGH_FLOOD_CELLS + LOW_FLOOD_CELLS}).scalars().all())
        missing = set(HIGH_FLOOD_CELLS + LOW_FLOOD_CELLS) - scored
        if missing:
            raise SystemExit(f"Chosen demo cells are not scored — refusing to seed a lie: {missing}")

        # clean prior demo (cascade deletes facilities/securities/positions)
        s.execute(text("DELETE FROM funds WHERE org_id = :o AND name = 'Nordkap Global Equity Fund'"), {"o": ASSET_MGR_ORG})
        s.execute(text("DELETE FROM issuers WHERE lei IN ('DEMOIBERIAFOODS0001','DEMONORDICSOFT0001','DEMOGLOBLOGIS0001')"))

        fund_id = s.execute(text("""
            INSERT INTO funds (org_id, name, fund_type, sfdr_classification, base_currency)
            VALUES (:o, 'Nordkap Global Equity Fund', 'fund', 'article_8', 'EUR')
            RETURNING fund_id
        """), {"o": ASSET_MGR_ORG}).scalar()

        leis = {"Iberia Foods SA": "DEMOIBERIAFOODS0001", "Nordic Software AB": "DEMONORDICSOFT0001",
                "Global Logistics NV": "DEMOGLOBLOGIS0001"}
        n_fac = 0
        for name, itype, country, sector, nace, aclass, isin, facilities in ISSUERS:
            issuer_id = s.execute(text("""
                INSERT INTO issuers (lei, name, issuer_type, country, sector, nace_code)
                VALUES (:lei, :n, :t, :c, :sec, :nace) RETURNING issuer_id
            """), {"lei": leis[name], "n": name, "t": itype, "c": country, "sec": sector, "nace": nace}).scalar()

            for fname, ftype, cell, weight, basis in facilities:
                lat, lon = latlon(cell)
                s.execute(text("""
                    INSERT INTO issuer_facilities
                        (issuer_id, name, facility_type, latitude, longitude, h3_cell, country, materiality_weight, weight_basis)
                    VALUES (:iid, :n, :t, :lat, :lon, :cell, :c, :w, :b)
                """), {"iid": issuer_id, "n": fname, "t": ftype, "lat": lat, "lon": lon,
                       "cell": cell, "c": country, "w": weight, "b": basis})
                n_fac += 1

            sec_id = s.execute(text("""
                INSERT INTO securities (isin, name, issuer_id, asset_class, currency)
                VALUES (:isin, :n, :iid, :ac, 'EUR') RETURNING security_id
            """), {"isin": isin, "n": f"{name} {'shares' if aclass=='equity' else 'bond'}",
                   "iid": issuer_id, "ac": aclass}).scalar()

            mv = {"Iberia Foods SA": 40_000_000, "Nordic Software AB": 25_000_000,
                  "Global Logistics NV": 15_000_000}[name]
            s.execute(text("""
                INSERT INTO fund_positions (fund_id, security_id, market_value_eur, weight_pct, as_of_date)
                VALUES (:f, :sec, :mv, :w, CURRENT_DATE)
            """), {"f": fund_id, "sec": sec_id, "mv": mv, "w": round(100 * mv / 80_000_000, 4)})

        print(f"Seeded fund {fund_id} with 3 issuers, {n_fac} facilities, 3 positions (€80.0m book).")


if __name__ == "__main__":
    main()
