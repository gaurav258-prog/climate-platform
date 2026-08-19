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
#  facilities: [(name, type, cell, weight, basis)],
#  emissions: (scope1, scope2, scope3, revenue_eur) or None)
ISSUERS = [
    # THE physical demonstration issuer: HQ safe, plants exposed. Footprint model
    # must score it High on PHYSICAL even though its HQ cell is low-flood.
    # Modest emitter → low transition. Shows physical-high / transition-low.
    ("Iberia Foods SA", "corporate", "ES", "Food manufacturing", "10.89", "equity", "ES00FOODS001", [
        ("Madrid HQ", "hq", LOW_FLOOD_CELLS[0], 0.10, "revenue"),
        ("Valencia Plant 1", "plant", HIGH_FLOOD_CELLS[0], 0.35, "revenue"),
        ("Valencia Plant 2", "plant", HIGH_FLOOD_CELLS[1], 0.30, "revenue"),
        ("Valencia Warehouse", "warehouse", HIGH_FLOOD_CELLS[2], 0.25, "revenue"),
    ], (45_000, 30_000, 400_000, 900_000_000)),
    # A genuinely low-risk issuer on both axes: safe footprint, tiny emissions.
    ("Nordic Software AB", "corporate", "SE", "Software", "62.01", "equity", "SE00SOFT0001", [
        ("Stockholm HQ", "hq", LOW_FLOOD_CELLS[1], 0.60, "revenue"),
        ("Malmo Office", "office", LOW_FLOOD_CELLS[2], 0.40, "revenue"),
    ], (500, 2_000, 15_000, 600_000_000)),
    # Partially-covered footprint (exercises scored_weight_pct disclosure).
    ("Global Logistics NV", "corporate", "NL", "Logistics", "52.10", "corporate_bond", "NL00LOGIS001", [
        ("Rotterdam Hub", "warehouse", HIGH_FLOOD_CELLS[3], 0.50, "assets"),
        ("Unscored Depot", "warehouse", "8801234567fffff", 0.50, "assets"),  # deliberately not in canonical_scores
    ], (120_000, 40_000, 800_000, 500_000_000)),
    # THE transition demonstration issuer: a fossil utility. Footprint sits in
    # SAFE cells (low physical) but huge emissions + a stranding sector (NACE 35)
    # → High TRANSITION. Proves the two dimensions are orthogonal — the physical
    # engine alone would have called this issuer safe.
    ("Continental Energy SE", "corporate", "DE", "Electric utilities", "35.11", "equity", "DE00ENERGY01", [
        ("Cologne HQ", "hq", LOW_FLOOD_CELLS[0], 0.20, "assets"),
        ("Coal Plant North", "plant", LOW_FLOOD_CELLS[1], 0.45, "production_capacity"),
        ("Gas Plant South", "plant", LOW_FLOOD_CELLS[2], 0.35, "production_capacity"),
    ], (18_000_000, 500_000, 6_000_000, 22_000_000_000)),
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

        leis = {"Iberia Foods SA": "DEMOIBERIAFOODS0001", "Nordic Software AB": "DEMONORDICSOFT0001",
                "Global Logistics NV": "DEMOGLOBLOGIS0001", "Continental Energy SE": "DEMOCONTENERGY01"}
        market_values = {"Iberia Foods SA": 40_000_000, "Nordic Software AB": 25_000_000,
                         "Global Logistics NV": 15_000_000, "Continental Energy SE": 20_000_000}
        book_total = sum(market_values.values())

        # clean prior demo (cascade deletes facilities/securities/positions/emissions)
        s.execute(text("DELETE FROM funds WHERE org_id = :o AND name = 'Nordkap Global Equity Fund'"), {"o": ASSET_MGR_ORG})
        s.execute(text("DELETE FROM issuers WHERE lei = ANY(:leis)"), {"leis": list(leis.values())})

        fund_id = s.execute(text("""
            INSERT INTO funds (org_id, name, fund_type, sfdr_classification, base_currency)
            VALUES (:o, 'Nordkap Global Equity Fund', 'fund', 'article_8', 'EUR')
            RETURNING fund_id
        """), {"o": ASSET_MGR_ORG}).scalar()

        n_fac = 0
        for name, itype, country, sector, nace, aclass, isin, facilities, emissions in ISSUERS:
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

            if emissions:
                s1, s2, s3, rev = emissions
                s.execute(text("""
                    INSERT INTO issuer_emissions (issuer_id, reporting_year, scope1_tco2e, scope2_tco2e, scope3_tco2e, revenue_eur, source)
                    VALUES (:iid, 2024, :s1, :s2, :s3, :rev, 'disclosed')
                """), {"iid": issuer_id, "s1": s1, "s2": s2, "s3": s3, "rev": rev})

            sec_id = s.execute(text("""
                INSERT INTO securities (isin, name, issuer_id, asset_class, currency)
                VALUES (:isin, :n, :iid, :ac, 'EUR') RETURNING security_id
            """), {"isin": isin, "n": f"{name} {'shares' if aclass=='equity' else 'bond'}",
                   "iid": issuer_id, "ac": aclass}).scalar()

            mv = market_values[name]
            s.execute(text("""
                INSERT INTO fund_positions (fund_id, security_id, market_value_eur, weight_pct, as_of_date)
                VALUES (:f, :sec, :mv, :w, CURRENT_DATE)
            """), {"f": fund_id, "sec": sec_id, "mv": mv, "w": round(100 * mv / book_total, 4)})

        # run the transition model over the seeded issuers (populates issuer_transition_scores)
        from services.scoring.transition_scoring import score_all_issuers
        summary = score_all_issuers(s)

        print(f"Seeded fund {fund_id}: {len(ISSUERS)} issuers, {n_fac} facilities, "
              f"{len(ISSUERS)} positions (€{book_total/1e6:.0f}m book).")
        print(f"Transition model: {summary}")


if __name__ == "__main__":
    main()
