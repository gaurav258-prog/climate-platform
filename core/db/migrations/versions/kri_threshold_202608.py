"""KRI appetite thresholds — a per-org RAG band on each Key Regulatory Indicator, so a KRI is a monitored
control against risk appetite (green / amber / red), not just a displayed number. Org rows override the
platform defaults (org_id NULL), exactly like approval_policy / decision_playbook.

Revision ID: kri_threshold_202608
Revises: decision_watchlist_202608
"""
from alembic import op

revision = "kri_threshold_202608"
down_revision = "decision_watchlist_202608"
branch_labels = None
depends_on = None

UP = """
CREATE TABLE IF NOT EXISTS kri_threshold (
    threshold_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       UUID REFERENCES organizations(org_id),        -- NULL = platform default
    framework    TEXT NOT NULL,
    kri_key      TEXT NOT NULL,
    amber        DOUBLE PRECISION,                              -- band edge (in the KRI's own unit)
    red          DOUBLE PRECISION,
    direction    TEXT NOT NULL DEFAULT 'higher_worse' CHECK (direction IN ('higher_worse','lower_worse')),
    updated_by   UUID REFERENCES users(user_id),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_kri_threshold_org ON kri_threshold(org_id, framework, kri_key) WHERE org_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_kri_threshold_default ON kri_threshold(framework, kri_key) WHERE org_id IS NULL;

-- platform-default appetite bands (each org can override in Settings → KRI appetite)
INSERT INTO kri_threshold (org_id, framework, kri_key, amber, red, direction)
SELECT NULL, v.framework, v.kri_key, v.amber, v.red, v.direction
FROM (VALUES
    ('bank_tcfd',       'pct_at_risk',  15, 30, 'higher_worse'),
    ('bank_tcfd',       'coverage',     80, 60, 'lower_worse'),
    ('reit_tcfd',       'pct_at_risk',  15, 30, 'higher_worse'),
    ('reit_tcfd',       'noi_impact',    5, 10, 'higher_worse'),
    ('reit_tcfd',       'coverage',     80, 60, 'lower_worse'),
    ('insurer_climate', 'loss_ratio',   60, 80, 'higher_worse'),
    ('insurer_climate', 'coverage',     80, 60, 'lower_worse'),
    ('csrd_e1',         'pct_at_risk',  15, 30, 'higher_worse'),
    ('csrd_e1',         'coverage',     80, 60, 'lower_worse'),
    ('sfdr_pai',        'emissions_cov',50, 30, 'lower_worse')
) AS v(framework, kri_key, amber, red, direction)
WHERE NOT EXISTS (
    SELECT 1 FROM kri_threshold k WHERE k.org_id IS NULL AND k.framework = v.framework AND k.kri_key = v.kri_key
);
"""

DOWN = "DROP TABLE IF EXISTS kri_threshold;"


def upgrade() -> None:
    op.execute(UP)


def downgrade() -> None:
    op.execute(DOWN)
