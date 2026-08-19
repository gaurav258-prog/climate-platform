"""Default appetite bands for the Pillar-3-specific transition KRIs (Templates 3 & 4).

These two KRIs exist only on the Pillar 3 ESG tab (TCFD does not prescribe them): the IEA-NZE2050
alignment-metric distance and exposure to the top-20 carbon-intensive firms. Both higher-worse.

Revision ID: kri_p3_transition_202608
Revises: kri_bank_decision_202608
"""
from alembic import op

revision = "kri_p3_transition_202608"
down_revision = "kri_bank_decision_202608"
branch_labels = None
depends_on = None

UP = """
INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction)
SELECT NULL, 'bank_p3esg', v.kri_key, v.amber, v.red, 'higher_worse'
FROM (VALUES
    ('p3_alignment', 20, 40),
    ('p3_top20', 5, 10)
) AS v(kri_key, amber, red)
WHERE NOT EXISTS (
    SELECT 1 FROM kri_threshold k WHERE k.org_id IS NULL AND k.framework = 'bank_p3esg' AND k.kri_key = v.kri_key
);
"""

DOWN = "DELETE FROM kri_threshold WHERE org_id IS NULL AND framework='bank_p3esg' AND kri_key IN ('p3_alignment','p3_top20');"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
