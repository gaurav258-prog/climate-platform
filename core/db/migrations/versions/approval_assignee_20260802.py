"""Add an optional assignee to approval_requests — route a pending request to a specific approver.

4-eyes already lets any decider (other than the maker) action a pending request. Assignment adds a light
routing layer on top: a maker or a decider can hand a request to a named approver so it lands on that
person's plate, without changing who is *allowed* to decide. Nullable — an unassigned request behaves
exactly as before (any decider can pick it up).

Revision ID: approval_assignee_202608
Revises: climbaseline_latlon_202608
"""
from alembic import op

revision = "approval_assignee_202608"
down_revision = "climbaseline_latlon_202608"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE approval_requests ADD COLUMN IF NOT EXISTS "
               "assigned_to_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL")


def downgrade():
    op.execute("ALTER TABLE approval_requests DROP COLUMN IF EXISTS assigned_to_user_id")
