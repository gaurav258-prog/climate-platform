"""Enforce ONE active canonical_scores row per (cell, hazard, scenario, horizon, lane).

The consolidated engine review found duplicate active rows accumulating from a non-atomic
check-then-insert race in the on-demand point scorers. The plot view was hardened with DISTINCT ON,
but the durable fix is to make duplicates structurally impossible: a UNIQUE partial index on active
rows. The point scorers now INSERT ... ON CONFLICT DO NOTHING so a race is a harmless no-op (the
loser reads the winner's value); the retire-first writers (engine, batch scripts) are unaffected
because after they retire the prior active row there is nothing to conflict with.

Idempotent: retires any residual duplicate active rows (keep latest per key) before creating the
index, so it is safe to run on any database state.

Revision ID: canonical_uniq_active_202608
Revises: sc_plot_distinct_202608
"""
from alembic import op

revision = "canonical_uniq_active_202608"
down_revision = "sc_plot_distinct_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # retire residual duplicate active rows (keep the most-recent per full key incl. lane)
    op.execute("""
        UPDATE canonical_scores SET valid_to = now()
        WHERE valid_to IS NULL AND score_id IN (
            SELECT score_id FROM (
                SELECT score_id, ROW_NUMBER() OVER (
                    PARTITION BY h3_cell, hazard_type, scenario, time_horizon, score_lane
                    ORDER BY scored_at DESC, score_id) rn
                FROM canonical_scores WHERE valid_to IS NULL) x
            WHERE rn > 1);
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_canonical_active_key
        ON canonical_scores (h3_cell, hazard_type, scenario, time_horizon, score_lane)
        WHERE valid_to IS NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_canonical_active_key;")
