"""Customer data intake — phase 2: column-mapping profiles, staging, asset matching.

  * intake_mapping_profiles — how one customer source's columns map onto a Tellumen template (column renames, unit
    scaling, currency conversion, value vocabularies). Versioned and immutable: a change is a new version, so every
    batch records exactly which mapping produced its values.
  * intake_staged_records — every row of every checked batch, as the engine WOULD receive it: the canonical values,
    accepted/rejected with the reasons, and how it matched the live book (new / update / unchanged / ambiguous,
    with the before→after of every changed field). The engine never reads this table; promotion does.
  * portfolio_entities / sc_sourcing_plots — external_ref (the customer's own asset id) is the primary match key;
    unique per org + book where given, so the same id can never become two assets.

Revision ID: intake_staging_20260925
Revises: intake_pipeline_20260925
"""
from typing import Sequence, Union

from alembic import op

revision: str = "intake_staging_20260925"
down_revision: Union[str, None] = "intake_pipeline_20260925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_mapping_profiles (
            profile_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id       UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            template     TEXT NOT NULL,
            name         TEXT NOT NULL,
            version      INTEGER NOT NULL,
            column_map   JSONB NOT NULL,
            transforms   JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by   UUID NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, template, name, version)
        )
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_mapping_profile_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'intake_mapping_profiles are versioned and immutable — save a new version; % is blocked', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_mapping_profile_worm ON intake_mapping_profiles")
    op.execute("CREATE TRIGGER trg_mapping_profile_worm BEFORE UPDATE OR DELETE ON intake_mapping_profiles "
               "FOR EACH ROW EXECUTE FUNCTION prevent_mapping_profile_mutation()")

    op.execute("""
        ALTER TABLE ingest_batches
            ADD COLUMN IF NOT EXISTS mapping_profile_id UUID REFERENCES intake_mapping_profiles(profile_id),
            ADD COLUMN IF NOT EXISTS mapping_report JSONB,
            ADD COLUMN IF NOT EXISTS match_summary JSONB
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_staged_records (
            batch_id          UUID NOT NULL REFERENCES ingest_batches(batch_id) ON DELETE CASCADE,
            row_no            INTEGER NOT NULL,
            status            TEXT NOT NULL,
            record            JSONB NOT NULL,
            problems          JSONB NOT NULL DEFAULT '[]'::jsonb,
            match_status      TEXT,
            target_entity_id  UUID,
            diff              JSONB,
            PRIMARY KEY (batch_id, row_no),
            CONSTRAINT ck_staged_status CHECK (status IN ('accepted', 'rejected')),
            CONSTRAINT ck_staged_match CHECK (match_status IS NULL OR match_status IN ('new', 'update', 'unchanged', 'ambiguous'))
        )
    """)

    op.execute("ALTER TABLE sc_sourcing_plots ADD COLUMN IF NOT EXISTS external_ref TEXT")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_pe_external_ref ON portfolio_entities (org_id, vertical, external_ref)
                  WHERE external_ref IS NOT NULL AND source = 'own'""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_plot_external_ref ON sc_sourcing_plots (org_id, external_ref)
                  WHERE external_ref IS NOT NULL""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_plot_external_ref")
    op.execute("DROP INDEX IF EXISTS ux_pe_external_ref")
    op.execute("ALTER TABLE sc_sourcing_plots DROP COLUMN IF EXISTS external_ref")
    op.execute("DROP TABLE IF EXISTS intake_staged_records")
    op.execute("ALTER TABLE ingest_batches DROP COLUMN IF EXISTS mapping_profile_id, DROP COLUMN IF EXISTS mapping_report, DROP COLUMN IF EXISTS match_summary")
    op.execute("DROP TABLE IF EXISTS intake_mapping_profiles")
    op.execute("DROP FUNCTION IF EXISTS prevent_mapping_profile_mutation()")
