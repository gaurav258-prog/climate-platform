"""Register calc/reporting-config changes in the approval matrix (audit T6).

These actions are always audited; whether they need 4-eyes is governed by the same approval_policy matrix
as location edits. Seed platform defaults with requires_approval = FALSE so there is NO change to today's
behaviour — an org opts into 4-eyes for config by toggling these in the matrix. material_fields '[]' means
"any change is material" once an org turns it on.

Revision ID: config_policy_actions_20260731
Revises: snapshot_worm_20260731
"""
from alembic import op

revision = "config_policy_actions_20260731"
down_revision = "snapshot_worm_20260731"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO approval_policy (org_id, action_key, requires_approval, material_fields)
        VALUES (NULL, 'config.reporting_settings', FALSE, '[]'::jsonb),
               (NULL, 'config.calc_settings',      FALSE, '[]'::jsonb)
        ON CONFLICT (action_key) WHERE org_id IS NULL DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM approval_policy WHERE org_id IS NULL "
               "AND action_key IN ('config.reporting_settings', 'config.calc_settings')")
