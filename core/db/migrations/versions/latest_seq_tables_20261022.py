"""The last of the tables read for their latest row by a timestamp are read in the order they were written (E315; the
latest-by-sequence rule, E51/E52; the worklist E312 left).

now() is the same for every row one transaction writes, so a timestamp cannot say which of two rows came last:

  feed_refresh_log    a feed's latest refresh            + seq (identity): the latest refresh per feed is the highest
  gl_balance          the latest ledger batch             + seq (identity): the latest batch holds the highest
  loan_arrears        the latest arrears batch            + seq (identity): the latest batch holds the highest
  model_risk_review   a model's latest review             + seq (identity): the latest review per model is the highest
  ingest_batches      the last batch imported             + imported_seq: a batch is imported by an update, so an insert
                                                            sequence would not order imports — drawn from its own
                                                            sequence by a trigger when the batch becomes 'imported'
                                                            (a terminal state) and never changed afterwards

Rows already recorded are numbered by their timestamp, then the order they were written (the writing transaction, then
its statement: xmin, cmin), then their id; imported batches by imported_at, then state_changed_at, then the same. The
downgrade removes exactly what this added.

Revision ID: latest_seq_tables_20261022
Revises: decision_signal_20261022
"""
from typing import Sequence, Union

from alembic import op

revision: str = "latest_seq_tables_20261022"
down_revision: Union[str, None] = "decision_signal_20261022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# table, its timestamp, its id, the index the 'latest' read uses (its leading columns)
_NUMBERED = (("feed_refresh_log", "created_at", "refresh_id", "feed_key"),
             ("gl_balance", "uploaded_at", "gl_id", "org_id"),
             ("loan_arrears", "uploaded_at", "arrears_id", "org_id"),
             ("model_risk_review", "reviewed_at", "review_id", "org_id, model_ref"))


def upgrade() -> None:
    for table, at, key, lead in _NUMBERED:
        op.execute(f"""
            ALTER TABLE {table} ADD COLUMN seq BIGINT;
            UPDATE {table} x SET seq = o.n
              FROM (SELECT {key}, row_number() OVER (ORDER BY {at}, xmin::text::bigint, cmin::text::bigint, {key}) AS n
                    FROM {table}) o
             WHERE x.{key} = o.{key};
            ALTER TABLE {table} ALTER COLUMN seq SET NOT NULL;
            ALTER TABLE {table} ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY;
            SELECT setval(pg_get_serial_sequence('{table}', 'seq'), COALESCE((SELECT max(seq) FROM {table}), 0) + 1, false);
            ALTER TABLE {table} ADD CONSTRAINT {table}_seq_key UNIQUE (seq);
            CREATE INDEX ix_{table}_seq ON {table} ({lead}, seq DESC);
        """)
    op.execute("""
        CREATE SEQUENCE ingest_batches_imported_seq;
        ALTER TABLE ingest_batches ADD COLUMN imported_seq BIGINT;
        ALTER SEQUENCE ingest_batches_imported_seq OWNED BY ingest_batches.imported_seq;
        UPDATE ingest_batches b SET imported_seq = o.n
          FROM (SELECT batch_id, row_number() OVER (ORDER BY imported_at, state_changed_at, xmin::text::bigint,
                                                             cmin::text::bigint, batch_id) AS n
                FROM ingest_batches WHERE state = 'imported') o
         WHERE b.batch_id = o.batch_id;
        SELECT setval('ingest_batches_imported_seq', COALESCE((SELECT max(imported_seq) FROM ingest_batches), 0) + 1, false);
        ALTER TABLE ingest_batches ADD CONSTRAINT ck_ingest_batch_imported_seq
            CHECK (state <> 'imported' OR imported_seq IS NOT NULL);
        ALTER TABLE ingest_batches ADD CONSTRAINT ingest_batches_imported_seq_key UNIQUE (imported_seq);

        CREATE FUNCTION ingest_batch_imported_seq() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND OLD.imported_seq IS NOT NULL THEN
                NEW.imported_seq := OLD.imported_seq;                    -- the order of an import is fixed once made
            ELSIF NEW.state = 'imported' THEN
                NEW.imported_seq := nextval('ingest_batches_imported_seq');
            ELSE
                NEW.imported_seq := NULL;
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_ingest_batch_imported_seq BEFORE INSERT OR UPDATE ON ingest_batches
            FOR EACH ROW EXECUTE FUNCTION ingest_batch_imported_seq();
        CREATE INDEX ix_ingest_batches_imported_seq ON ingest_batches (org_id, imported_seq DESC);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX ix_ingest_batches_imported_seq;
        DROP TRIGGER trg_ingest_batch_imported_seq ON ingest_batches;
        DROP FUNCTION ingest_batch_imported_seq();
        ALTER TABLE ingest_batches DROP CONSTRAINT ingest_batches_imported_seq_key,
            DROP CONSTRAINT ck_ingest_batch_imported_seq, DROP COLUMN imported_seq;
    """)
    for table, _at, _key, _lead in reversed(_NUMBERED):
        op.execute(f"""
            DROP INDEX ix_{table}_seq;
            ALTER TABLE {table} DROP CONSTRAINT {table}_seq_key, DROP COLUMN seq;
        """)
