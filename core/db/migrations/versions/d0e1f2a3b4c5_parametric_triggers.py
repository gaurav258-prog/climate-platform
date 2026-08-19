"""parametric_triggers

Insurance's "Parametric" tab (catalog.js Trigger monitoring) was a
workflow=null placeholder -- the Tellumen_Explainer_Extended.pptx deck
described it as a real feature ("automatic payouts the moment real data
crosses a threshold") before it existed. This adds the real thing: one
trigger config per policy (which hazard, and the attachment/exhaustion
score band a real parametric/cat-bond payout curve scales across -- see
ml/scoring/parametric_trigger.py), computed live off the SAME
canonical_scores-derived hazard scores every other insurance view already
reads (v_insurance_policy_physical_risk) -- no new event feed, no separate
data path.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS insurance_policy_triggers (
    policy_id        UUID PRIMARY KEY REFERENCES insurance_policies(policy_id) ON DELETE CASCADE,
    hazard_type      VARCHAR(30) NOT NULL,
    attachment_score NUMERIC(5,2) NOT NULL,
    exhaustion_score NUMERIC(5,2) NOT NULL,
    updated_by       UUID REFERENCES users(user_id) ON DELETE SET NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (exhaustion_score > attachment_score)
);
"""

DOWNGRADE = "DROP TABLE IF EXISTS insurance_policy_triggers;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
