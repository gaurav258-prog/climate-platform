"""Add an extensible interpretation JSONB to org_calc_settings.

The governed interpretation-switch layer (services/calc_settings.py) stores the open-ended set of
regulatory-interpretation choices (e.g. the catastrophe PML return period — Solvency II 1-in-200 vs a
rating-agency 1-in-250) in one JSONB column, so a new switch is code-only with no further migration.

Revision ID: org_calc_interp_202608
Revises: kri_task_source_202608
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "org_calc_interp_202608"
down_revision = "kri_task_source_202608"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("org_calc_settings",
                  sa.Column("interpretation", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade():
    op.drop_column("org_calc_settings", "interpretation")
