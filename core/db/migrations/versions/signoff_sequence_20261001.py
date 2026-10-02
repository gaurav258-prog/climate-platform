"""Sign-offs of a regulatory spec are read in the order they were written (E109; the rule of E51/E52/E86): two people
signing in one transaction share now(), so ordering by signed_at returned them in any order.

regspec_signoff gets `seq` (an identity, assigned at insert and never changed). Existing rows are numbered by the time
they recorded (then their id).

Revision ID: signoff_sequence_20261001
Revises: eudr_filing_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "signoff_sequence_20261001"
down_revision: Union[str, None] = "eudr_filing_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE regspec_signoff ADD COLUMN seq BIGINT;
        ALTER TABLE regspec_signoff DISABLE TRIGGER USER;   -- the append-only guard: numbering existing rows is not an edit
        UPDATE regspec_signoff x SET seq = o.n
          FROM (SELECT signoff_id, row_number() OVER (ORDER BY signed_at, signoff_id) AS n FROM regspec_signoff) o
         WHERE x.signoff_id = o.signoff_id;
        ALTER TABLE regspec_signoff ENABLE TRIGGER USER;
        ALTER TABLE regspec_signoff ALTER COLUMN seq SET NOT NULL;
        ALTER TABLE regspec_signoff ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY;
        SELECT setval(pg_get_serial_sequence('regspec_signoff', 'seq'), COALESCE((SELECT max(seq) FROM regspec_signoff), 0) + 1, false);
        ALTER TABLE regspec_signoff ADD CONSTRAINT ux_regspec_signoff_seq UNIQUE (seq);
        CREATE INDEX ix_regspec_signoff_by_seq ON regspec_signoff (framework, version, seq);
    """)


def downgrade() -> None:
    op.execute("""DROP INDEX ix_regspec_signoff_by_seq; ALTER TABLE regspec_signoff DROP CONSTRAINT ux_regspec_signoff_seq;
                  ALTER TABLE regspec_signoff DROP COLUMN seq;""")
