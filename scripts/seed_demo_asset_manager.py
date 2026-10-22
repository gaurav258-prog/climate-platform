"""Seed a realistic demo asset-manager book on the new holdings foundation
(migration f8a9b0c1d2e3), to prove the footprint model end-to-end against the
REAL golden source — no fabricated scores.

The demonstration case is the exact failure mode of the old single-point model:
an issuer whose HQ sits in a low-hazard cell but whose PRODUCTION PLANTS (the
bulk of its materiality) sit in high-flood cells. The old "one lat/lon = HQ"
model scores it safe; the footprint model scores it High because the plants
dominate the materiality-weighted roll-up.

Each site sits where its name says, in the country it states (E317: the sites once sat on the
only cells scored then, near Valencia, while named and stated as Cologne, Stockholm or Rotterdam;
corrected 2026-10-22 by the product owner's decision — scripts/seed_demo_issuer_sites.py moves an
existing book's sites in place). A site's cell is scored on demand, like any address, so its
scores are whatever the maps say there; the depot's location is not known (partial coverage).

Idempotent: wipes and re-inserts the demo fund/issuers for the asset-manager org.
Run: .venv/bin/python scripts/seed_demo_asset_manager.py
"""
from sqlalchemy import text

from core.db.session import get_session

ASSET_MGR_ORG = "44444444-4444-4444-8444-444444444444"  # Nordkap Asset Management (demo)

# Where each demo site is: (latitude, longitude, region) — the place its name says (a city, or for the two unnamed
# plants a north and a south German city, as decided 2026-10-22); None: the location is not known.
SITES = {
    "Madrid HQ": (40.4168, -3.7038, "Madrid"),
    "Valencia Plant 1": (39.49938, -0.89986, "Valencia"),
    "Valencia Plant 2": (39.19939, -0.89694, "Valencia"),
    "Valencia Warehouse": (39.49993, -1.00521, "Valencia"),
    "Stockholm HQ": (59.3326, 18.0649, "Stockholm"),
    "Malmo Office": (55.6050, 13.0038, "Skåne"),
    "Rotterdam Hub": (51.9225, 4.47917, "South Holland"),
    "Unscored Depot": None,
    "Cologne HQ": (50.9375, 6.9603, "North Rhine-Westphalia"),
    "Coal Plant North": (53.5511, 9.9937, "Hamburg"),
    "Gas Plant South": (48.1351, 11.5820, "Bavaria"),
}


# (name, issuer_type, country, sector, nace, asset_class, isin,
#  facilities: [(name, type, weight, basis)] — placed by SITES,
#  emissions: (scope1, scope2, scope3, revenue_eur) or None)
ISSUERS = [
    # THE physical demonstration issuer: HQ safe, plants exposed. Footprint model
    # must score it High on PHYSICAL even though its HQ cell is low-flood.
    # Modest emitter → low transition. Shows physical-high / transition-low.
    ("Iberia Foods SA", "corporate", "ES", "Food manufacturing", "10.89", "equity", "ES00FOODS001", [
        ("Madrid HQ", "hq", 0.10, "revenue"),
        ("Valencia Plant 1", "plant", 0.35, "revenue"),
        ("Valencia Plant 2", "plant", 0.30, "revenue"),
        ("Valencia Warehouse", "warehouse", 0.25, "revenue"),
    ], (45_000, 30_000, 400_000, 900_000_000)),
    # A genuinely low-risk issuer on both axes: safe footprint, tiny emissions.
    ("Nordic Software AB", "corporate", "SE", "Software", "62.01", "equity", "SE00SOFT0001", [
        ("Stockholm HQ", "hq", 0.60, "revenue"),
        ("Malmo Office", "office", 0.40, "revenue"),
    ], (500, 2_000, 15_000, 600_000_000)),
    # Partially-covered footprint (exercises scored_weight_pct disclosure).
    ("Global Logistics NV", "corporate", "NL", "Logistics", "52.10", "corporate_bond", "NL00LOGIS001", [
        ("Rotterdam Hub", "warehouse", 0.50, "assets"),
        ("Unscored Depot", "warehouse", 0.50, "assets"),  # location not known: partial coverage
    ], (120_000, 40_000, 800_000, 500_000_000)),
    # THE transition demonstration issuer: a fossil utility. Footprint sits in
    # SAFE cells (low physical) but huge emissions + a stranding sector (NACE 35)
    # → High TRANSITION. Proves the two dimensions are orthogonal — the physical
    # engine alone would have called this issuer safe.
    ("Continental Energy SE", "corporate", "DE", "Electric utilities", "35.11", "equity", "DE00ENERGY01", [
        ("Cologne HQ", "hq", 0.20, "assets"),
        ("Coal Plant North", "plant", 0.45, "production_capacity"),
        ("Gas Plant South", "plant", 0.35, "production_capacity"),
    ], (18_000_000, 500_000, 6_000_000, 22_000_000_000)),
]


def place(name: str) -> dict:
    """A site's latitude, longitude, H3 cell (res 8, as canonical_scores) and region — all None when not known."""
    import h3
    at = SITES[name]
    if at is None:
        return {"lat": None, "lon": None, "cell": None, "region": None}
    return {"lat": at[0], "lon": at[1], "cell": h3.latlng_to_cell(at[0], at[1], 8), "region": at[2]}


LEIS = {"Iberia Foods SA": "DEMOIBERIAFOODS0001", "Nordic Software AB": "DEMONORDICSOFT0001",
        "Global Logistics NV": "DEMOGLOBLOGIS0001", "Continental Energy SE": "DEMOCONTENERGY01"}


def main():
    with get_session() as s:
        leis = LEIS
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

            for fname, ftype, weight, basis in facilities:
                s.execute(text("""
                    INSERT INTO issuer_facilities (issuer_id, name, facility_type, latitude, longitude, h3_cell, country,
                                                   region, materiality_weight, weight_basis)
                    VALUES (:iid, :n, :t, :lat, :lon, :cell, :c, :region, :w, :b)
                """), {"iid": issuer_id, "n": fname, "t": ftype, "c": country, "w": weight, "b": basis, **place(fname)})
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

        print(f"Seeded fund {fund_id}: {len(ISSUERS)} issuers, {n_fac} facilities, "
              f"{len(ISSUERS)} positions (€{book_total/1e6:.0f}m book).")
    from scripts.seed_demo_issuer_sites import score
    print(score())


if __name__ == "__main__":
    main()
