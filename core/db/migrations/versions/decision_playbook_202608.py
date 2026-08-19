"""Decision playbook — the per-customer map of 'which decision → which automated downstream actions', set at
onboarding beside the approval matrix. Each row is (org_id, action) with the automations to run WHEN the
decision is approved; org rows override the platform default (org_id NULL).

Platform defaults preserve today's behaviour: engage / reprice / disclose spin a Kanban card; the new
automations (notify, flag-for-disclosure, watchlist, webhook) are OFF until a customer turns them on.

Revision ID: decision_playbook_202608
Revises: decision_policy_202608
"""
from alembic import op

revision = "decision_playbook_202608"
down_revision = "decision_policy_202608"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE IF NOT EXISTS decision_playbook (
    org_id           UUID REFERENCES organizations(org_id),         -- NULL = platform default
    action           TEXT NOT NULL CHECK (action IN ('reprice','engage','disclose','monitor','accept')),
    spin_task        BOOLEAN NOT NULL DEFAULT FALSE,   -- create a Kanban card
    assignee_user_id UUID REFERENCES users(user_id),   -- route the card to (NULL = unassigned)
    due_days         INTEGER,                          -- card due date = approval + due_days
    notify           BOOLEAN NOT NULL DEFAULT FALSE,   -- email the owner
    flag_disclosure  BOOLEAN NOT NULL DEFAULT FALSE,   -- flag the exposure for the next climate filing
    watchlist        BOOLEAN NOT NULL DEFAULT FALSE,   -- add to the monitoring watchlist + schedule a re-check
    webhook          BOOLEAN NOT NULL DEFAULT FALSE,   -- emit risk.decision.approved to registered endpoints
    updated_by       UUID REFERENCES users(user_id),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_playbook_org ON decision_playbook(org_id, action) WHERE org_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_playbook_default ON decision_playbook(action) WHERE org_id IS NULL;

-- platform defaults (org_id NULL): keep the current spin-a-card behaviour; new automations opt-in
INSERT INTO decision_playbook (org_id, action, spin_task, due_days) VALUES
    (NULL, 'reprice',  TRUE, 30),
    (NULL, 'engage',   TRUE, 14),
    (NULL, 'disclose', TRUE, 21),
    (NULL, 'monitor',  FALSE, NULL),
    (NULL, 'accept',   FALSE, NULL)
ON CONFLICT DO NOTHING;
"""

DOWN = "DROP TABLE IF EXISTS decision_playbook;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
