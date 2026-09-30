"""Own operational sites join the intake pipeline: the customer's own site id (external_ref), unique per organisation.

Sites were written by a CSV route outside intake (no security inspection, no checks, no matching — a re-sent file
duplicated every site). As an intake sector (services.ingest.sector_ingest.SITES) a site is matched on the customer's
own id first, like every other book (services/intake/matching.py).

Revision ID: site_intake_20260930
Revises: latest_by_sequence_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "site_intake_20260930"
down_revision: Union[str, None] = "latest_by_sequence_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000fee8"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'manufacturer', 'ES');
                 INSERT INTO sc_company_sites (org_id, name, external_ref) VALUES ('{_PROBE_ORG}', 'probe site', 'SITE-1');""",
    "cleanup": f"""DELETE FROM sc_company_sites WHERE org_id = '{_PROBE_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE sc_company_sites ADD COLUMN external_ref TEXT;
        CREATE UNIQUE INDEX ux_site_external_ref ON sc_company_sites (org_id, external_ref) WHERE external_ref IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM sc_company_sites WHERE external_ref IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade site_intake_20260930: sites carry the customer''s own id, which matches '
                                'the next file to them';
            END IF;
        END $$;
    """)
    op.execute("DROP INDEX ux_site_external_ref; ALTER TABLE sc_company_sites DROP COLUMN external_ref;")
