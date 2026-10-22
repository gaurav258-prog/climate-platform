"""Decisions say which signal raised them, and are read in the order they were written (losses into decisions, the
product owner's decisions of 2026-10-22; the latest-by-sequence rule, E51/E52).

The decision spine had one signal: an exposure crossing the institution's stated at-risk level by a scenario and
horizon. Tested losses are the second: an asset whose tested expected yearly loss is at or above the share of its
value the institution states (method.loss_signal_share). A decision, the watch it opens and the disclosure flag it
raises now carry their signal:

  risk_decision             + signal ('crossing' | 'loss'); a loss decision is on today's climate (baseline, current)
                            + seq: an identity, unique — the standing call is the latest decision by seq, never by
                              decided_at (now() is the same for every row one transaction writes)
  decision_watchlist        + signal; + baseline_share, last_share: a loss watch is re-checked on the asset's tested
                              loss share, a crossing watch on its projected score — each in its own columns
                            one open watch per exposure and signal (was: per exposure)
  decision_disclosure_flag  + signal; one open flag per exposure and signal (was: per exposure)

Rows already recorded are crossings. Decisions already recorded are numbered by decided_at, then the order they were
written (the writing transaction, then its statement: xmin, cmin), then their id. The downgrade refuses while a loss
decision, watch or flag exists — the earlier schema cannot hold one — and otherwise removes exactly what this added.

Revision ID: decision_signal_20261022
Revises: validation_run_seq_20261018
"""
from typing import Sequence, Union

from alembic import op

revision: str = "decision_signal_20261022"
down_revision: Union[str, None] = "validation_run_seq_20261018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ORG = "0bbe0bbe-0000-4000-8000-000000de5161"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{ORG}', 'refusal probe', 'insurer', 'DE');
                INSERT INTO risk_decision (org_id, entity_id, entity_name, scenario, horizon, action, status, signal)
                VALUES ('{ORG}', gen_random_uuid(), 'probe', 'baseline', 'current', 'monitor', 'approved', 'loss');""",
    "cleanup": f"""DELETE FROM risk_decision WHERE org_id = '{ORG}';
                  DELETE FROM organizations WHERE org_id = '{ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE risk_decision ADD COLUMN signal TEXT NOT NULL DEFAULT 'crossing',
            ADD CONSTRAINT risk_decision_signal_check CHECK (signal IN ('crossing', 'loss')),
            ADD CONSTRAINT risk_decision_loss_today_check
                CHECK (signal <> 'loss' OR (scenario = 'baseline' AND horizon = 'current'));
        ALTER TABLE risk_decision ADD COLUMN seq BIGINT;
        UPDATE risk_decision x SET seq = o.n
          FROM (SELECT decision_id,
                       row_number() OVER (ORDER BY decided_at, xmin::text::bigint, cmin::text::bigint, decision_id) AS n
                FROM risk_decision) o
         WHERE x.decision_id = o.decision_id;
        ALTER TABLE risk_decision ALTER COLUMN seq SET NOT NULL;
        ALTER TABLE risk_decision ALTER COLUMN seq ADD GENERATED ALWAYS AS IDENTITY;
        SELECT setval(pg_get_serial_sequence('risk_decision', 'seq'), COALESCE((SELECT max(seq) FROM risk_decision), 0) + 1, false);
        ALTER TABLE risk_decision ADD CONSTRAINT risk_decision_seq_key UNIQUE (seq);
        CREATE INDEX ix_risk_decision_signal_seq ON risk_decision (org_id, signal, entity_id, seq DESC);

        ALTER TABLE decision_watchlist ADD COLUMN signal TEXT NOT NULL DEFAULT 'crossing',
            ADD COLUMN baseline_share DOUBLE PRECISION, ADD COLUMN last_share DOUBLE PRECISION,
            ADD CONSTRAINT decision_watchlist_signal_check CHECK (signal IN ('crossing', 'loss')),
            ADD CONSTRAINT decision_watchlist_measure_check CHECK (
                (signal = 'crossing' AND baseline_share IS NULL AND last_share IS NULL)
             OR (signal = 'loss' AND baseline_score IS NULL AND last_score IS NULL AND last_delta IS NULL));
        DROP INDEX ux_watchlist_open;
        CREATE UNIQUE INDEX ux_watchlist_open ON decision_watchlist (org_id, entity_id, signal) WHERE status = 'watching';

        ALTER TABLE decision_disclosure_flag ADD COLUMN signal TEXT NOT NULL DEFAULT 'crossing',
            ADD CONSTRAINT decision_disclosure_flag_signal_check CHECK (signal IN ('crossing', 'loss'));
        DROP INDEX ux_disclosure_flag_open;
        CREATE UNIQUE INDEX ux_disclosure_flag_open ON decision_disclosure_flag (org_id, entity_id, signal) WHERE status = 'open';
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM risk_decision WHERE signal = 'loss')
               OR EXISTS (SELECT 1 FROM decision_watchlist WHERE signal = 'loss')
               OR EXISTS (SELECT 1 FROM decision_disclosure_flag WHERE signal = 'loss')
            THEN RAISE EXCEPTION 'loss-signal decisions exist: the schema before decision_signal_20261022 cannot hold them';
            END IF;
        END $$;
        DROP INDEX ux_disclosure_flag_open;
        CREATE UNIQUE INDEX ux_disclosure_flag_open ON decision_disclosure_flag (org_id, entity_id) WHERE status = 'open';
        ALTER TABLE decision_disclosure_flag DROP CONSTRAINT decision_disclosure_flag_signal_check, DROP COLUMN signal;

        DROP INDEX ux_watchlist_open;
        CREATE UNIQUE INDEX ux_watchlist_open ON decision_watchlist (org_id, entity_id) WHERE status = 'watching';
        ALTER TABLE decision_watchlist DROP CONSTRAINT decision_watchlist_measure_check,
            DROP CONSTRAINT decision_watchlist_signal_check, DROP COLUMN last_share, DROP COLUMN baseline_share,
            DROP COLUMN signal;

        DROP INDEX ix_risk_decision_signal_seq;
        ALTER TABLE risk_decision DROP CONSTRAINT risk_decision_seq_key, DROP COLUMN seq,
            DROP CONSTRAINT risk_decision_loss_today_check, DROP CONSTRAINT risk_decision_signal_check, DROP COLUMN signal;
    """)
