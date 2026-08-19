"""Add a 'returned' status to approval_requests — the checker can send a request back for more info.

Beyond approve/reject, a checker can return a request to the maker with a note ("send back / request
more info"). It is not a terminal decision like reject: the maker sees the note and can revise and
resubmit. Widens the status CHECK constraint to allow 'returned'.

Revision ID: approval_returned_202608
Revises: reporting_entities_202608
"""
from alembic import op

revision = "approval_returned_202608"
down_revision = "reporting_entities_202608"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE approval_requests DROP CONSTRAINT approval_requests_status_check")
    op.execute("ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_status_check "
               "CHECK (status IN ('pending','approved','rejected','returned'))")


def downgrade():
    op.execute("ALTER TABLE approval_requests DROP CONSTRAINT approval_requests_status_check")
    op.execute("ALTER TABLE approval_requests ADD CONSTRAINT approval_requests_status_check "
               "CHECK (status IN ('pending','approved','rejected'))")
