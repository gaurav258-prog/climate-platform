"""Allow 'decision' as a regulatory_task source — a Kanban card spun from an approved forward-risk decision
(engage / reprice / disclose) so the follow-up work is tracked on the board.

Revision ID: task_source_decision_202608
Revises: risk_decision_4eyes_202608
"""
from alembic import op

revision = "task_source_decision_202608"
down_revision = "risk_decision_4eyes_202608"
branch_labels = None
depends_on = None

UP = """
ALTER TABLE regulatory_task DROP CONSTRAINT IF EXISTS regulatory_task_source_check;
ALTER TABLE regulatory_task ADD CONSTRAINT regulatory_task_source_check
    CHECK (source IN ('manual','validation','exception','obligation','regulatory_change','decision'));
"""
DOWN = """
ALTER TABLE regulatory_task DROP CONSTRAINT IF EXISTS regulatory_task_source_check;
ALTER TABLE regulatory_task ADD CONSTRAINT regulatory_task_source_check
    CHECK (source IN ('manual','validation','exception','obligation','regulatory_change'));
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
