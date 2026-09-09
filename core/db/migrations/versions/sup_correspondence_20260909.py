"""Formal correspondence: every request or finding carries a reference number, a legal basis, a response period, a
signed letter (PDF) and the entity's formal receipt; each authority numbers its own letters.

Revision ID: sup_correspondence_20260909
Revises: sup_respondent_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_correspondence_20260909"
down_revision: Union[str, None] = "sup_respondent_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""ALTER TABLE supervision_request
                  ADD COLUMN IF NOT EXISTS reference        TEXT,
                  ADD COLUMN IF NOT EXISTS legal_basis      JSONB,
                  ADD COLUMN IF NOT EXISTS response_days    INTEGER,
                  ADD COLUMN IF NOT EXISTS signatory        TEXT,
                  ADD COLUMN IF NOT EXISTS letter_pdf       BYTEA,
                  ADD COLUMN IF NOT EXISTS letter_sha256    TEXT,
                  ADD COLUMN IF NOT EXISTS issued_at        TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS receipt_at       TIMESTAMPTZ,
                  ADD COLUMN IF NOT EXISTS receipt_by       UUID""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_sup_request_reference ON supervision_request (regulator_org_id, reference) WHERE reference IS NOT NULL")
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_reference_counter (
            regulator_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            year              INTEGER NOT NULL,
            next_no           INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (regulator_org_id, year)
        )
    """)
    op.execute("ALTER TABLE supervisor_settings ADD COLUMN IF NOT EXISTS reference_prefix TEXT, ADD COLUMN IF NOT EXISTS signatory_title TEXT")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervisor_reference_counter")
    op.execute("""ALTER TABLE supervision_request DROP COLUMN IF EXISTS reference, DROP COLUMN IF EXISTS legal_basis, DROP COLUMN IF EXISTS response_days,
                  DROP COLUMN IF EXISTS signatory, DROP COLUMN IF EXISTS letter_pdf, DROP COLUMN IF EXISTS letter_sha256, DROP COLUMN IF EXISTS issued_at,
                  DROP COLUMN IF EXISTS receipt_at, DROP COLUMN IF EXISTS receipt_by""")
    op.execute("ALTER TABLE supervisor_settings DROP COLUMN IF EXISTS reference_prefix, DROP COLUMN IF EXISTS signatory_title")
