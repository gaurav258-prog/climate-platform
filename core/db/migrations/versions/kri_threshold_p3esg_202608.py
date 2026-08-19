"""Default appetite bands for the bank Pillar 3 ESG KRIs (mirror the bank_tcfd climate defaults).

Revision ID: kri_threshold_p3esg_202608
Revises: protected_h3_cell_202608
"""
from alembic import op

revision = "kri_threshold_p3esg_202608"
down_revision = "protected_h3_cell_202608"
branch_labels = None
depends_on = None

UP = """
INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction)
SELECT NULL, v.framework, v.kri_key, v.amber, v.red, v.direction
FROM (VALUES
    ('bank_p3esg', 'pct_at_risk', 15, 30, 'higher_worse'),
    ('bank_p3esg', 'coverage',    80, 60, 'lower_worse')
) AS v(framework, kri_key, amber, red, direction)
WHERE NOT EXISTS (
    SELECT 1 FROM kri_threshold k WHERE k.org_id IS NULL AND k.framework = v.framework AND k.kri_key = v.kri_key
);
"""

DOWN = "DELETE FROM kri_threshold WHERE org_id IS NULL AND framework='bank_p3esg';"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
