"""A loss is computed on the value its damage curve is a share of (E171).

A building damage curve gives damage as a share of the BUILDING's value (the measured US curve: building damage over
the building's actual cash value, both as the adjuster recorded them). The books held no such value outside insurance:
a property book states market value (land included), a loan tape the collateral's appraised value, a holding a
position. So the property and loan books gain the building's own value, stated by the institution; without it a
flood loss on those books is a named gap, never a market value read as a building value.

  ext_realestate  + building_value_eur   the building's own value, land excluded
  ext_banking     + building_value_eur   the collateral building's own value, land excluded

Downgrade refuses while a building value is recorded.

Revision ID: loss_value_20261006
Revises: loss_band_20261006
"""
from typing import Sequence, Union

from alembic import op

revision: str = "loss_value_20261006"
down_revision: Union[str, None] = "loss_band_20261006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-000000000172', 'refusal probe', 'reit', 'DE');
                INSERT INTO portfolio_entities (entity_id, org_id, vertical, entity_name, primary_value_eur, source)
                VALUES ('aaaaaaaa-0000-4000-8000-000000000171', '0bbe0bbe-0000-4000-8000-000000000172', 'realestate', 'probe', 1, 'own');
                INSERT INTO ext_realestate (entity_id, annual_noi_eur, building_value_eur)
                VALUES ('aaaaaaaa-0000-4000-8000-000000000171', 1, 1);""",
    "cleanup": """DELETE FROM ext_realestate WHERE entity_id = 'aaaaaaaa-0000-4000-8000-000000000171';
                  DELETE FROM portfolio_entities WHERE entity_id = 'aaaaaaaa-0000-4000-8000-000000000171';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-000000000172';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE ext_realestate ADD COLUMN building_value_eur numeric(18,2) CHECK (building_value_eur > 0);
        ALTER TABLE ext_banking ADD COLUMN building_value_eur numeric(18,2) CHECK (building_value_eur > 0);
        COMMENT ON COLUMN ext_realestate.building_value_eur IS 'The building''s own value, land excluded (E171)';
        COMMENT ON COLUMN ext_banking.building_value_eur IS 'The collateral building''s own value, land excluded (E171)';
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM ext_realestate WHERE building_value_eur IS NOT NULL)
               OR EXISTS (SELECT 1 FROM ext_banking WHERE building_value_eur IS NOT NULL) THEN
                RAISE EXCEPTION 'building values are recorded — they cannot be removed';
            END IF;
        END $$;
        ALTER TABLE ext_banking DROP COLUMN building_value_eur;
        ALTER TABLE ext_realestate DROP COLUMN building_value_eur;
    """)
