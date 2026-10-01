"""EUDR layer 2 (E92 — intake): what the governed intake needs to land EUDR records.

  sc_suppliers / sc_customers.external_ref   the undertaking's own id for a supplier or customer, so a book sent again
                                              updates the party instead of adding it twice, and a movement or plot file can
                                              name it (one id per organisation)
  sc_sourcing_plots.coordinate_decimals      the decimals the plot's coordinates were sent with: Art. 2(28) of Regulation
                                              (EU) 2023/1115 — geolocation 'using at least six decimal digits'. Stored as
                                              sent (a float cannot say how many digits it was given with); NULL = not known
                                              (a plot from before this, or located without coordinates).

Revision ID: eudr_intake_20261001
Revises: eudr_foundation_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_intake_20261001"
down_revision: Union[str, None] = "eudr_foundation_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000fef0"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'manufacturer', 'NL');
                 INSERT INTO sc_suppliers (org_id, name, external_ref) VALUES ('{_ORG}', 'probe supplier', 'SUP-1');""",
    "cleanup": f"""DELETE FROM sc_suppliers WHERE org_id = '{_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE sc_suppliers ADD COLUMN external_ref TEXT;
        ALTER TABLE sc_customers ADD COLUMN external_ref TEXT;
        CREATE UNIQUE INDEX ux_sc_suppliers_ref ON sc_suppliers (org_id, external_ref) WHERE external_ref IS NOT NULL;
        CREATE UNIQUE INDEX ux_sc_customers_ref ON sc_customers (org_id, external_ref) WHERE external_ref IS NOT NULL;
        ALTER TABLE sc_sourcing_plots ADD COLUMN coordinate_decimals SMALLINT
            CONSTRAINT ck_plot_coordinate_decimals CHECK (coordinate_decimals IS NULL OR coordinate_decimals BETWEEN 0 AND 15);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM sc_suppliers WHERE external_ref IS NOT NULL)
               OR EXISTS (SELECT 1 FROM sc_customers WHERE external_ref IS NOT NULL)
               OR EXISTS (SELECT 1 FROM sc_sourcing_plots WHERE coordinate_decimals IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade eudr_intake_20261001: parties carry your ids or plots their coordinate precision';
            END IF;
        END $$;
    """)
    op.execute("""
        ALTER TABLE sc_sourcing_plots DROP COLUMN coordinate_decimals;
        DROP INDEX ux_sc_customers_ref; DROP INDEX ux_sc_suppliers_ref;
        ALTER TABLE sc_customers DROP COLUMN external_ref;
        ALTER TABLE sc_suppliers DROP COLUMN external_ref;
    """)
