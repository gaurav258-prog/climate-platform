"""Default appetite bands for the new SFDR PAI value KRIs (fossil-fuel exposure, non-renewable energy).
The other PAI values (carbon footprint, WACI) have no universal appetite — left ungraded until an org sets one.

Revision ID: kri_threshold_sfdr_202608
Revises: kri_threshold_202608
"""
from alembic import op

revision = "kri_threshold_sfdr_202608"
down_revision = "kri_threshold_202608"
branch_labels = None
depends_on = None

UP = """
INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction)
SELECT NULL, v.framework, v.kri_key, v.amber, v.red, v.direction
FROM (VALUES
    ('sfdr_pai', 'fossil_fuel',    5, 10, 'higher_worse'),
    ('sfdr_pai', 'non_renewable', 50, 75, 'higher_worse')
) AS v(framework, kri_key, amber, red, direction)
WHERE NOT EXISTS (
    SELECT 1 FROM kri_threshold k WHERE k.org_id IS NULL AND k.framework = v.framework AND k.kri_key = v.kri_key
);
"""

DOWN = "DELETE FROM kri_threshold WHERE org_id IS NULL AND framework='sfdr_pai' AND kri_key IN ('fossil_fuel','non_renewable');"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
