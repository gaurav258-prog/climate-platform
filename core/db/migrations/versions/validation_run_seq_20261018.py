"""The validation record is read in the order it was written (E216; the latest-by-sequence rule, E51/E52).

validation_run is write-once (trg_validation_run_immutable), and its readers took 'the latest run' — per hazard for
Model risk, per model, per published crop fit — by created_at. now() is the same for every row one transaction writes
(a calibration batch records many runs at once), so the timestamp could not say which came last.

  validation_run  + seq: an identity, unique; 'latest' is the highest seq

Rows already recorded are numbered by the time they recorded, then — within one transaction, where that time ties — by
the order they were written (the writing transaction, then its statement: xmin, cmin), then their id; as
history_sequences_20261002 did, the immutability trigger is set aside for that one numbering (numbering a row is not an
edit of it — every recorded value is checked unchanged before the trigger returns). Storage order is not write order
here: rolled-back inserts leave space that later rows fill. The downgrade drops the column.

Revision ID: validation_run_seq_20261018
Revises: feed_cause_20261018
"""
from typing import Sequence, Union

from alembic import op

revision: str = "validation_run_seq_20261018"
down_revision: Union[str, None] = "feed_cause_20261018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# every value a run recorded, as one fingerprint: the numbering must leave each of them as it was
_RECORDED = ("md5(row(v.run_id, v.model_id, v.hazard_type, v.scope, v.horizon, v.kind, v.method, v.target_source, "
             "v.n_samples, v.metrics, v.skill_grade, v.passed_gate, v.gate, v.notes, v.code_version, v.data_vintage, "
             "v.created_by, v.created_at)::text)")


def upgrade() -> None:
    op.execute(f"""
        CREATE TEMP TABLE _vr_before ON COMMIT DROP AS SELECT run_id, {_RECORDED} AS h FROM validation_run v;
        ALTER TABLE validation_run ADD COLUMN seq BIGINT;
        ALTER TABLE validation_run DISABLE TRIGGER trg_validation_run_immutable;   -- numbering a row is not an edit of it
        UPDATE validation_run x SET seq = o.n
          FROM (SELECT run_id, row_number() OVER (ORDER BY created_at, xmin::text::bigint, cmin::text::bigint, run_id) AS n
                FROM validation_run) o
         WHERE x.run_id = o.run_id;
        ALTER TABLE validation_run ENABLE TRIGGER trg_validation_run_immutable;
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM validation_run v JOIN _vr_before b USING (run_id) WHERE {_RECORDED} <> b.h)
               OR (SELECT count(*) FROM validation_run) <> (SELECT count(*) FROM _vr_before)
            THEN RAISE EXCEPTION 'numbering the validation record changed a recorded value';
            END IF;
        END $$;
        ALTER TABLE validation_run ALTER COLUMN seq SET NOT NULL;
        ALTER TABLE validation_run ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY;
        SELECT setval(pg_get_serial_sequence('validation_run', 'seq'), COALESCE((SELECT max(seq) FROM validation_run), 0) + 1, false);
        ALTER TABLE validation_run ADD CONSTRAINT validation_run_seq_key UNIQUE (seq);
        CREATE INDEX ix_validation_run_hazard_seq ON validation_run (hazard_type, seq DESC);
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX ix_validation_run_hazard_seq;
        ALTER TABLE validation_run DROP CONSTRAINT validation_run_seq_key, DROP COLUMN seq;
    """)
