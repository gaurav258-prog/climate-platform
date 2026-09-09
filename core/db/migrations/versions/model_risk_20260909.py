"""Model-risk register — the organisation's independent review record over the models its figures rest on.

Revision ID: model_risk_20260909
Revises: controls_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "model_risk_20260909"
down_revision: Union[str, None] = "controls_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS model_risk_review (
            review_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id           UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            model_ref        TEXT NOT NULL,             -- 'model:<model_id>' or 'calibration:<commodity_id>:<origin>:<hazard>'
            reviewer_user_id UUID NOT NULL REFERENCES users(user_id),
            conclusion       TEXT NOT NULL,             -- fit_for_use | restricted_use | not_fit
            comment          TEXT,
            evidence_sha256  TEXT NOT NULL,             -- hash of the model card the reviewer saw
            next_review_by   DATE,
            reviewed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_model_risk_review ON model_risk_review (org_id, model_ref, reviewed_at DESC);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_risk_review;")
