"""Filings are read in the order they were made (E116; the rule of E51/E52/E86/E109): two filings made in one transaction
share now(), so 'the latest filing' or 'newest first' by created_at came back in either order (found when a simplified
declaration and its update were listed).

regulatory_filing gets `seq` (an identity, assigned at insert and never changed). Existing rows are numbered by the time
they recorded, then their id.

Revision ID: filing_sequence_20261002
Revises: eudr_declaration_20261002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "filing_sequence_20261002"
down_revision: Union[str, None] = "eudr_declaration_20261002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE regulatory_filing ADD COLUMN seq BIGINT;
        ALTER TABLE regulatory_filing DISABLE TRIGGER USER;   -- numbering existing rows is not an edit of a filing
        UPDATE regulatory_filing x SET seq = o.n
          FROM (SELECT filing_id, row_number() OVER (ORDER BY created_at, filing_id) AS n FROM regulatory_filing) o
         WHERE x.filing_id = o.filing_id;
        ALTER TABLE regulatory_filing ENABLE TRIGGER USER;
        ALTER TABLE regulatory_filing ALTER COLUMN seq SET NOT NULL;
        ALTER TABLE regulatory_filing ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY;
        SELECT setval(pg_get_serial_sequence('regulatory_filing', 'seq'), COALESCE((SELECT max(seq) FROM regulatory_filing), 0) + 1, false);
        ALTER TABLE regulatory_filing ADD CONSTRAINT ux_regulatory_filing_seq UNIQUE (seq);
        CREATE INDEX ix_regulatory_filing_by_seq ON regulatory_filing (org_id, framework, seq);
    """)


def downgrade() -> None:
    op.execute("""DROP INDEX ix_regulatory_filing_by_seq; ALTER TABLE regulatory_filing DROP CONSTRAINT ux_regulatory_filing_seq;
                  ALTER TABLE regulatory_filing DROP COLUMN seq;""")
