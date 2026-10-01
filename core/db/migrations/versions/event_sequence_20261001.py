"""History tables are read in the order they were written, by a strictly increasing number — never by a timestamp
(E86; the rule of E51/E52). now() is the same for every row one transaction writes: a task moved todo → review → done by
one supervision message, a filing's lifecycle steps, a thread's messages could come back in any order.

Each table gets `seq` (an identity, assigned at insert and never changed). Existing rows are numbered by the time they
recorded (then their id): rows written in one transaction before this migration keep an order nobody recorded — the
readers show them in that numbered order from now on.

Revision ID: event_sequence_20261001
Revises: equity_rule_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "event_sequence_20261001"
down_revision: Union[str, None] = "equity_rule_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table → (its id column, the column a history is read by)
TABLES = {
    "regulatory_task_event": ("event_id", "task_id"),
    "regulatory_filing_event": ("event_id", "filing_id"),
    "supervision_request_message": ("message_id", "request_id"),
    "reg_case_message": ("message_id", "case_id"),
    "model_status_event": ("event_id", "model_id"),
}


def upgrade() -> None:
    for t, (pk, parent) in TABLES.items():
        op.execute(f"""
            ALTER TABLE {t} ADD COLUMN seq BIGINT;
            ALTER TABLE {t} DISABLE TRIGGER USER;          -- the append-only guard: numbering existing rows is not an edit
            UPDATE {t} x SET seq = o.n FROM (SELECT {pk}, row_number() OVER (ORDER BY created_at, {pk}) AS n FROM {t}) o
             WHERE x.{pk} = o.{pk};
            ALTER TABLE {t} ENABLE TRIGGER USER;
            ALTER TABLE {t} ALTER COLUMN seq SET NOT NULL;
            ALTER TABLE {t} ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY;
            SELECT setval(pg_get_serial_sequence('{t}', 'seq'), COALESCE((SELECT max(seq) FROM {t}), 0) + 1, false);
            ALTER TABLE {t} ADD CONSTRAINT ux_{t}_seq UNIQUE (seq);
            CREATE INDEX ix_{t}_by_seq ON {t} ({parent}, seq);
        """)


def downgrade() -> None:
    for t in TABLES:
        op.execute(f"DROP INDEX ix_{t}_by_seq; ALTER TABLE {t} DROP CONSTRAINT ux_{t}_seq; ALTER TABLE {t} DROP COLUMN seq;")
