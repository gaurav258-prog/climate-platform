"""Respondent entities (supervised, not on Tellumen as a workspace): submission channel on supervisor_submissions and the portal permission.

Revision ID: sup_respondent_20260909
Revises: sup_deadlines_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_respondent_20260909"
down_revision: Union[str, None] = "sup_deadlines_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE supervisor_submissions ADD COLUMN IF NOT EXISTS channel TEXT NOT NULL DEFAULT 'supervisor_upload'")
    op.execute("INSERT INTO permissions (code, description) VALUES ('respondent.portal', "
               "'Use the supervisory portal: acknowledge, state attributes, submit templates, answer requests') ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    op.execute("ALTER TABLE supervisor_submissions DROP COLUMN IF EXISTS channel")
