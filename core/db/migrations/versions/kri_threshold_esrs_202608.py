"""Default appetite bands for the ESRS pack (E1 climate + E3 water + E4 biodiversity) KRIs. The agri/
manufacturer KRI dashboard reports the full nature pack (esrs_pack); these bands mirror the csrd_e1 climate
defaults and add water-stress + EUDR-deforestation bands.

Revision ID: kri_threshold_esrs_202608
Revises: kri_threshold_sfdr_202608
"""
from alembic import op

revision = "kri_threshold_esrs_202608"
down_revision = "kri_threshold_sfdr_202608"
branch_labels = None
depends_on = None

UP = """
INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction)
SELECT NULL, v.framework, v.kri_key, v.amber, v.red, v.direction
FROM (VALUES
    ('esrs_pack', 'pct_at_risk',            15, 30, 'higher_worse'),
    ('esrs_pack', 'coverage',               80, 60, 'lower_worse'),
    ('esrs_pack', 'water_peak',             40, 60, 'higher_worse'),
    ('esrs_pack', 'deforestation_free_pct', 99, 95, 'lower_worse'),
    ('esrs_pack', 'non_compliant',           1,  3, 'higher_worse'),
    ('esrs_pack', 'forest_loss_ha',        0.1,  1, 'higher_worse')
) AS v(framework, kri_key, amber, red, direction)
WHERE NOT EXISTS (
    SELECT 1 FROM kri_threshold k WHERE k.org_id IS NULL AND k.framework = v.framework AND k.kri_key = v.kri_key
);
"""

DOWN = "DELETE FROM kri_threshold WHERE org_id IS NULL AND framework='esrs_pack';"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
