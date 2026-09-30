"""A located asset's postal code; the insurance 'CRESTA zone' number retired.

Solvency II places a risk in a nat-cat risk zone by its postal code (Del. Reg. (EU) 2015/35 Annex IX: 'The risk zones
... shall be equal to the postal code areas or administrative units in the following tables' — first 1 or 2 digits,
first 2 letters, or a table of codes, per region and peril). ext_insurance.cresta_zone held one integer per policy: it
could not hold a lettered zone (IE, UK), one number cannot stand for the different zones a risk falls in per peril,
and a CRESTA zone is not an Annex IX zone. It holds no value in any database this migration has run on; the postal
code is the fact, and the zone per peril is read from Annex IX (services.governance.solvency2_natcat_tables).

Revision ID: postal_code_20260930
Revises: country_iso_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "postal_code_20260930"
down_revision: Union[str, None] = "country_iso_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee2', 'refusal probe', 'insurer', 'DE');
                INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, latitude, longitude, country, primary_value_eur, postal_code)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee3', '0bbe0bbe-0000-4000-8000-00000000fee2', 'insurance', 'probe', 52.5, 13.4, 'DE', 1, '10115');""",
    "cleanup": """DELETE FROM portfolio_entities WHERE entity_id = '0bbe0bbe-0000-4000-8000-00000000fee3';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee2';""",
}


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM ext_insurance WHERE cresta_zone IS NOT NULL) THEN
                RAISE EXCEPTION 'postal_code_20260930: ext_insurance.cresta_zone holds values; a zone number cannot be '
                                'turned into a postal code — ask the insurer for the postal codes first';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE ext_insurance DROP COLUMN cresta_zone")
    op.execute("""ALTER TABLE portfolio_entities ADD COLUMN postal_code TEXT
                  CONSTRAINT ck_portfolio_entities_postal_code CHECK (postal_code ~ '^[0-9A-Z][0-9A-Z -]{0,11}$')""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM portfolio_entities WHERE postal_code IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade postal_code_20260930: postal codes are held, which the previous schema '
                                'cannot hold';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE portfolio_entities DROP COLUMN postal_code")
    op.execute("ALTER TABLE ext_insurance ADD COLUMN cresta_zone INTEGER")
