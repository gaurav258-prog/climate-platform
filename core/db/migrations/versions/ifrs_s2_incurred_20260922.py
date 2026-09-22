"""IFRS S2 ¶16(a) — actual, incurred NatCat losses for the reporting period.

Gap closed (independent audit pass): the platform's insurer disclosures had zero coverage of ACTUAL, incurred
current-period climate losses — only modelled/anticipated figures exist anywhere (EAL, standard-formula/
internal-model NatCat SCR — IFRS S2 ¶16(c)-(d)). ¶16(a) is a SEPARATE requirement: how climate-related risks
have affected financial position, performance and cash flows FOR THE REPORTING PERIOD, i.e. what actually
happened. This is real incurred-loss data the platform cannot compute or observe itself — it must come from
the insurer's own claims/financial records, customer-supplied (same honesty discipline as EVIC / REIT gross
revenue: an optional input, never fabricated, an honest "not yet supplied" state when absent).

Kept simple — a disclosure input, not a claims-management system: one row per (org, reporting period, peril).

Revision ID: ifrs_s2_incurred_20260922
Revises: d9d0702196df
"""
import sqlalchemy as sa
from alembic import op

revision = "ifrs_s2_incurred_20260922"
down_revision = "d9d0702196df"
branch_labels = None
depends_on = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS insurer_incurred_losses (
    loss_id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                    UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    period_start               DATE NOT NULL,
    period_end                 DATE NOT NULL,
    peril                      VARCHAR(30) NOT NULL,
    gross_incurred_loss_eur    NUMERIC(18,2) NOT NULL,
    net_incurred_loss_eur      NUMERIC(18,2),
    source                     VARCHAR(20) NOT NULL DEFAULT 'client',
    created_by                 UUID REFERENCES users(user_id) ON DELETE SET NULL,
    reported_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (period_end >= period_start),
    CHECK (gross_incurred_loss_eur >= 0),
    CHECK (net_incurred_loss_eur IS NULL OR net_incurred_loss_eur >= 0)
);
CREATE INDEX IF NOT EXISTS ix_insurer_incurred_losses_org_period
    ON insurer_incurred_losses (org_id, period_start DESC);
"""

DOWNGRADE = "DROP TABLE IF EXISTS insurer_incurred_losses;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
