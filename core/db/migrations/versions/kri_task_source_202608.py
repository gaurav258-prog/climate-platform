"""Allow 'kri' as a regulatory_task source — a task raised from a breached KRI on the KRI dashboard, so the
task carries its lineage (source='kri', source_ref='<framework>:<kri_key>') and de-dupes per indicator.

Revision ID: kri_task_source_202608
Revises: reported_filings_202608
"""
from alembic import op

revision = "kri_task_source_202608"
down_revision = "reported_filings_202608"
branch_labels = None
depends_on = None

_ALLOWED = "'manual','validation','exception','obligation','regulatory_change','decision'"

UP = f"""
ALTER TABLE regulatory_task DROP CONSTRAINT IF EXISTS regulatory_task_source_check;
ALTER TABLE regulatory_task ADD CONSTRAINT regulatory_task_source_check
    CHECK (source IN ({_ALLOWED}, 'kri'));
"""

DOWN = f"""
ALTER TABLE regulatory_task DROP CONSTRAINT IF EXISTS regulatory_task_source_check;
ALTER TABLE regulatory_task ADD CONSTRAINT regulatory_task_source_check
    CHECK (source IN ({_ALLOWED}));
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
