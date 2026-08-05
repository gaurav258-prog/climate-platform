"""Task attachments + @mentions — collaboration on the Kanban board.

Two additions to the regulatory-task workflow:
  • regulatory_task_attachment — a file attached to a task (stored inline as bytes; this is a self-contained
    deployment with no external blob store). Cascades with the task.
  • regulatory_task_mention — a colleague @mentioned in a task comment, so they can be pinged for a question,
    a clarification, or a delegation. Unread until the mentioned user opens the task (read_at set), which
    drives the in-app "mentions" inbox on the board.

Revision ID: reg_task_attach_mention_202608
Revises: filing_cell_override_202608
"""
from alembic import op

revision = "reg_task_attach_mention_202608"
down_revision = "filing_cell_override_202608"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE IF NOT EXISTS regulatory_task_attachment (
    attachment_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(org_id),
    task_id         UUID NOT NULL REFERENCES regulatory_task(task_id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    content_type    TEXT,
    size_bytes      INTEGER NOT NULL,
    data            BYTEA NOT NULL,
    uploaded_by     UUID REFERENCES users(user_id),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_task_attachment_task ON regulatory_task_attachment(task_id);

CREATE TABLE IF NOT EXISTS regulatory_task_mention (
    mention_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(org_id),
    task_id         UUID NOT NULL REFERENCES regulatory_task(task_id) ON DELETE CASCADE,
    mentioned_user  UUID NOT NULL REFERENCES users(user_id),
    by_user         UUID REFERENCES users(user_id),
    snippet         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at         TIMESTAMPTZ
);
-- the unread-mentions inbox query: by recipient, newest first, unread first
CREATE INDEX IF NOT EXISTS ix_task_mention_inbox ON regulatory_task_mention(mentioned_user, read_at, created_at);
"""

DROP = """
DROP TABLE IF EXISTS regulatory_task_mention;
DROP TABLE IF EXISTS regulatory_task_attachment;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
