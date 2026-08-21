"""Seed a demo INVESTMENT book for the insurer org (vertical='insurer_investments').

An insurer is an underwriter AND a large institutional investor; EIOPA/IFRS S2 require climate risk on both
sides. The liability/underwriting book is seeded elsewhere; this gives the insurer an asset book so the
investment-side combined climate-VaR (see api/routers/insurance.py::investments) is demonstrable. Idempotent:
copies a deterministic subset of the asset-manager demo holdings into the insurer org at scaled values, so the
positions are already at scored locations. The whole demo book is demo data, clearly a fixture.
"""
from sqlalchemy import text

from core.db.config import SessionLocal


def main():
    s = SessionLocal()
    iberia = s.execute(text("SELECT org_id FROM organizations WHERE type='insurer' LIMIT 1")).scalar()
    if not iberia:
        print("no insurer org — nothing to seed")
        return
    # widen the (stale, Alembic-only) vertical CHECK if present so the new vertical is allowed on the demo DB
    con = s.execute(text("SELECT 1 FROM pg_constraint WHERE conname='portfolio_entities_vertical_check'")).first()
    if con:
        s.execute(text("ALTER TABLE portfolio_entities DROP CONSTRAINT portfolio_entities_vertical_check"))
        s.execute(text("""ALTER TABLE portfolio_entities ADD CONSTRAINT portfolio_entities_vertical_check
            CHECK (vertical = ANY (ARRAY['banking','insurance','realestate','assetmgmt','insurer_investments']::text[]))"""))
    existing = s.execute(text("SELECT count(*) FROM portfolio_entities WHERE org_id=:o AND vertical='insurer_investments'"),
                         {"o": str(iberia)}).scalar()
    if existing:
        print(f"insurer investment book already seeded ({existing} holdings)")
        s.commit()
        return
    n = s.execute(text("""
        INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, entity_type, sector, nace_code,
            latitude, longitude, h3_cell, country, region, primary_value_eur, created_at, updated_at)
        SELECT gen_random_uuid(), CAST(:o AS uuid), 'insurer_investments',
            entity_name, entity_type, sector, nace_code, latitude, longitude, h3_cell, country, region,
            ROUND(CAST(primary_value_eur AS numeric)*0.6, 2), now(), now()
        FROM (SELECT *, row_number() OVER (ORDER BY entity_id) rn FROM portfolio_entities WHERE vertical='assetmgmt') t
        WHERE rn <= 40 RETURNING 1
    """), {"o": str(iberia)}).rowcount
    s.commit()
    print(f"seeded {n} insurer investment holdings")
    s.close()


if __name__ == "__main__":
    main()
