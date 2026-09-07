"""supervision_assignment — which people inside a supervisory organisation work which supervised entity.

Scope (supervision_scope) says what the ORGANISATION may see. Assignment says what a PERSON in it sees when
their role works a case list rather than the whole population (role 'scope' in supervision_profiles.json).

Revision ID: sup_assign_20260907
Revises: pe_external_ref_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_assign_20260907"
down_revision: Union[str, None] = "pe_external_ref_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_assignment (
            assignment_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regulator_org_id   UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            supervised_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            user_id            UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            capacity           TEXT NOT NULL DEFAULT 'lead',   -- lead | support (free text, shown as given)
            assigned_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            assigned_by        UUID REFERENCES users(user_id),
            revoked_at         TIMESTAMPTZ,
            revoked_by         UUID REFERENCES users(user_id)
        )
    """)
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_supervision_assignment_active
                  ON supervision_assignment (regulator_org_id, supervised_org_id, user_id) WHERE revoked_at IS NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_supervision_assignment_user
                  ON supervision_assignment (regulator_org_id, user_id) WHERE revoked_at IS NULL""")
    op.execute("INSERT INTO permissions (code, description) VALUES ('supervisor.assignments.manage', "
               "'Assign supervised entities to the people who work them') ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervision_assignment")
