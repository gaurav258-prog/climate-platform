"""Make forward-risk-decision 4-eyes a CUSTOMER choice, set at onboarding through the existing approval
matrix. Registers the 'risk.decision' action (platform default = NO approval, so it's opt-in — customers
decide) and adds an optional value THRESHOLD to the matrix (only decisions above the threshold need a second
approval; 0/NULL with approval on = always). WHO approves stays governed by RBAC (the Approver role).

Revision ID: decision_policy_202608
Revises: task_source_decision_202608
"""
from alembic import op

revision = "decision_policy_202608"
down_revision = "task_source_decision_202608"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE approval_policy ADD COLUMN IF NOT EXISTS threshold_eur NUMERIC;
-- platform default: forward-risk decisions do NOT require a second approval unless a customer turns it on
INSERT INTO approval_policy (org_id, action_key, requires_approval, material_fields)
VALUES (NULL, 'risk.decision', FALSE, '[]'::jsonb)
ON CONFLICT DO NOTHING;
"""

DOWN = """
DELETE FROM approval_policy WHERE org_id IS NULL AND action_key = 'risk.decision';
ALTER TABLE approval_policy DROP COLUMN IF EXISTS threshold_eur;
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
