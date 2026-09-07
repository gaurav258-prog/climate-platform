"""supervisor_submissions: a supervised entity's SUBMITTED template as ingested by its supervisor (Tier-2 intake).

One row per (regulator, subject entity, framework, template, period): the cells as mapped from the file, the basis
the entity states in its narrative (scenario / horizon / method), and provenance (file name, hash, who, when).
The regulator's own data — never visible to the subject entity or to other regulators.

Revision ID: sup_intake_20260907
Revises: sup_perms_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_intake_20260907"
down_revision: Union[str, None] = "sup_perms_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_submissions (
            submission_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regulator_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            subject_org_id    UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            framework         TEXT NOT NULL,
            template          TEXT NOT NULL,
            period_label      TEXT NOT NULL,
            basis             JSONB NOT NULL DEFAULT '{}'::jsonb,
            cells             JSONB NOT NULL,
            n_cells           INTEGER NOT NULL,
            source_file       TEXT,
            source_sha256     TEXT,
            column_mapping    JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by        UUID,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (regulator_org_id, subject_org_id, framework, template, period_label)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sup_sub_subject ON supervisor_submissions (regulator_org_id, subject_org_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervisor_submissions")
