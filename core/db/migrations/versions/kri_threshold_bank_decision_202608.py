"""Default appetite bands for the new bank decision/concentration KRIs.

Adds platform-default RAG bands for the three critical-but-missing KRIs surfaced on the bank dashboard
(both TCFD and Pillar 3 ESG): acute-peril exposure share, chronic-peril exposure share, projected
(forward) share-at-risk, and climate-sector concentration. Org rows still override these.

Revision ID: kri_bank_decision_202608
Revises: kri_threshold_p3esg_202608
"""
from alembic import op

revision = "kri_bank_decision_202608"
down_revision = "kri_threshold_p3esg_202608"
branch_labels = None
depends_on = None

# (framework, kri_key, amber, red, direction). All higher_worse — more exposure / concentration is worse.
# Forward share trips earlier than the point-in-time share (it is an early-warning signal). Concentration
# bands follow the usual single-name/sector concentration comfort zone.
_ROWS = ",\n    ".join(
    f"('{fw}', '{key}', {amber}, {red}, 'higher_worse')"
    for fw in ("bank_tcfd", "bank_p3esg")
    for key, amber, red in (
        ("acute_share", 12, 25),
        ("chronic_share", 20, 40),
        ("forward_share", 20, 35),
        ("sector_concentration", 50, 70),
    )
)

UP = f"""
INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction)
SELECT NULL, v.framework, v.kri_key, v.amber, v.red, v.direction
FROM (VALUES
    {_ROWS}
) AS v(framework, kri_key, amber, red, direction)
WHERE NOT EXISTS (
    SELECT 1 FROM kri_threshold k WHERE k.org_id IS NULL AND k.framework = v.framework AND k.kri_key = v.kri_key
);
"""

DOWN = """
DELETE FROM kri_threshold WHERE org_id IS NULL AND framework IN ('bank_tcfd','bank_p3esg')
  AND kri_key IN ('acute_share','chronic_share','forward_share','sector_concentration');
"""


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
