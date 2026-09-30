"""A filing's own disclosure date — the date the report is concluded / made, when it is not the day it is prepared.

Some reports are governed by the rules in force on the day they are made, not the day their figures describe
(specification basis 'disclosure_date'): an ORSA concluded after 30 January 2027 is governed by Art. 45a of Directive
2009/138/EC as amended by Directive (EU) 2025/2, a pre-emptive recovery plan submitted after that date by Directive (EU)
2025/1 — whenever it is prepared. regulatory_filing.disclosure_date is that planned date (NULL = the day the filing is
frozen, as before); it chooses the governing specification and is frozen with the filing.

Revision ID: filing_disclosure_date_20260930
Revises: provided_entity_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "filing_disclosure_date_20260930"
down_revision: Union[str, None] = "provided_entity_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee6', 'refusal probe', 'insurer', 'DE');
                INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, disclosure_date)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee6', 'insurer_solvency', '2025-12-31', 'FY2025', '2027-03-31');""",
    "cleanup": """DELETE FROM regulatory_filing WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee6';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee6';""",
}


def upgrade() -> None:
    op.execute("""ALTER TABLE regulatory_filing ADD COLUMN disclosure_date DATE
                  CONSTRAINT ck_regulatory_filing_disclosure_date CHECK (disclosure_date IS NULL OR disclosure_date > period_end)""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_filing WHERE disclosure_date IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade filing_disclosure_date_20260930: filings carry their own disclosure date, '
                                'which decides the rules they are governed by';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE regulatory_filing DROP COLUMN disclosure_date")
