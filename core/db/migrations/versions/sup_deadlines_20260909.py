"""Supervisor-set deadlines: the supervisory calendar per mandate and period, published to the entities' obligations
calendars, with the automatic reminders / overdue requests it raised.

Revision ID: sup_deadlines_20260909
Revises: sup_mandates_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_deadlines_20260909"
down_revision: Union[str, None] = "sup_mandates_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_deadline (
            deadline_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regulator_org_id   UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            mandate_id         TEXT NOT NULL,
            framework          TEXT NOT NULL,
            period_label       TEXT NOT NULL,
            period_end         DATE NOT NULL,
            due_date           DATE NOT NULL,
            due_source         TEXT NOT NULL DEFAULT 'registry',     -- registry (the act's rule) | set (the authority)
            note               TEXT,
            status             TEXT NOT NULL DEFAULT 'draft',        -- draft | published
            published_at       TIMESTAMPTZ,
            published_by       UUID,
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (regulator_org_id, mandate_id, period_label)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_deadline_notice (
            notice_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            deadline_id        UUID NOT NULL REFERENCES supervision_deadline(deadline_id) ON DELETE CASCADE,
            supervised_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            stage              TEXT NOT NULL,                        -- reminder | overdue
            request_id         UUID,
            sent_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (deadline_id, supervised_org_id, stage)
        )
    """)
    op.execute("""ALTER TABLE regulatory_obligation
                  ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'entity',
                  ADD COLUMN IF NOT EXISTS supervision_deadline_id UUID,
                  ADD COLUMN IF NOT EXISTS set_by TEXT""")
    op.execute("INSERT INTO permissions (code, description) VALUES ('supervisor.deadlines.manage', "
               "'Set and publish filing deadlines to the supervised population') ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervision_deadline_notice")
    op.execute("DROP TABLE IF EXISTS supervision_deadline")
    op.execute("ALTER TABLE regulatory_obligation DROP COLUMN IF EXISTS source, DROP COLUMN IF EXISTS supervision_deadline_id, DROP COLUMN IF EXISTS set_by")
