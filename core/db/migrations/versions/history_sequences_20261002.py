"""Twelve more histories are read in the order they were written (E118; the rule of E51/E52/E86/E109/E116): rows one
transaction writes share now(), so 'the latest challenger', a version history, an audit trail or the rows of one upload
ordered by their timestamp came back in any order.

Each table gets `seq` (an identity, assigned at insert and never changed). Existing rows are numbered by the time they
recorded, then their id.

Revision ID: history_sequences_20261002
Revises: filing_sequence_20261002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "history_sequences_20261002"
down_revision: Union[str, None] = "filing_sequence_20261002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table, primary key, the timestamp the rows were read by, the columns a reader filters on before seq
_TABLES = (
    ("model_registry", "model_id", "created_at", "hazard_type"),               # the latest challenger; the registry
    ("model_drift_observation", "obs_id", "created_at", "hazard_type"),        # drift history
    ("kri_threshold_version", "version_id", "created_at", "org_id, framework"),  # appetite-band audit trail
    ("asset_conflicts", "conflict_id", "created_at", "org_id"),                # one ingest raises many
    ("report_snapshots", "snapshot_id", "created_at", "org_id"),               # frozen-filing register
    ("access_audit_log", "audit_id", "created_at", "org_id"),                  # audit trail
    ("approval_requests", "request_id", "created_at", "org_id"),               # 4-eyes control evidence
    ("regulatory_task_mention", "mention_id", "created_at", "org_id, mentioned_user"),  # mentions inbox
    ("webhook_deliveries", "delivery_id", "created_at", "org_id"),             # one event fans out to every endpoint
    ("entity_structure_import_rows", "row_id", "created_at", "import_id"),     # the rows of one upload, in file order
    ("reported_figure", "figure_id", "created_at", "filing_id"),               # the figures of one filing, as read
    ("client_intake_user", "roster_id", "created_at", "intake_id"),            # the roster, as entered
)


def upgrade() -> None:
    for t, pk, ts, by in _TABLES:
        op.execute(f"""
            ALTER TABLE {t} ADD COLUMN seq BIGINT;
            ALTER TABLE {t} DISABLE TRIGGER USER;   -- numbering existing rows is not an edit of them
            UPDATE {t} x SET seq = o.n
              FROM (SELECT {pk}, row_number() OVER (ORDER BY {ts}, {pk}) AS n FROM {t}) o
             WHERE x.{pk} = o.{pk};
            ALTER TABLE {t} ENABLE TRIGGER USER;
            ALTER TABLE {t} ALTER COLUMN seq SET NOT NULL;
            ALTER TABLE {t} ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY;
            SELECT setval(pg_get_serial_sequence('{t}', 'seq'), COALESCE((SELECT max(seq) FROM {t}), 0) + 1, false);
            ALTER TABLE {t} ADD CONSTRAINT ux_{t}_seq UNIQUE (seq);
            CREATE INDEX ix_{t}_by_seq ON {t} ({by}, seq);
        """)


def downgrade() -> None:
    for t, _pk, _ts, _by in reversed(_TABLES):
        op.execute(f"DROP INDEX ix_{t}_by_seq; ALTER TABLE {t} DROP CONSTRAINT ux_{t}_seq; ALTER TABLE {t} DROP COLUMN seq;")
