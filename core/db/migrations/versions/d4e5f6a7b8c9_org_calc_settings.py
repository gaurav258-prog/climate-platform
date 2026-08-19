"""org_calc_settings -- customer-facing calculation-method triggers

Per-org opt-in switches for calculation methodology, alongside the existing
scenario/horizon query params. Every column defaults to today's exact fixed
behaviour -- an org that never visits a settings page gets IDENTICAL numbers
to before this migration. Choosing an option is a deliberate, visible action
(see ui/src/pages/admin/CalcSettingsPanel.jsx), never a silent behavior change.

- severity_model: 'universal' (today's one bucket->discount% table for every
  hazard) or 'peril_specific' (a wildfire VH plot is not priced the same as a
  flood VH plot -- see ml/scoring/valuation_discount.py's PERIL_DISCOUNT_PCT).
  Used by banking/real-estate/asset-management's valuation_block().
- assetmgmt_var_method: 'haircut' (today's relabeled deterministic haircut,
  disclosed as not a statistical VaR) or 'monte_carlo' (a real percentile-
  based portfolio loss distribution -- see ml/scoring/valuation_discount.py's
  monte_carlo_var()). Asset management only.
- insurance_return_period_model: 'fixed' (today's one 200/50/20/10-yr mapping
  for every peril) or 'peril_specific' (return periods calibrated per hazard
  -- see ml/scoring/insurance_pricing.py's PERIL_RETURN_PERIOD_YEARS).

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-07-09

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS org_calc_settings (
    org_id                          UUID PRIMARY KEY REFERENCES organizations(org_id) ON DELETE CASCADE,
    severity_model                  VARCHAR(20) NOT NULL DEFAULT 'universal'
                                     CHECK (severity_model IN ('universal', 'peril_specific')),
    assetmgmt_var_method            VARCHAR(20) NOT NULL DEFAULT 'haircut'
                                     CHECK (assetmgmt_var_method IN ('haircut', 'monte_carlo')),
    insurance_return_period_model   VARCHAR(20) NOT NULL DEFAULT 'fixed'
                                     CHECK (insurance_return_period_model IN ('fixed', 'peril_specific')),
    updated_by                      UUID REFERENCES users(user_id),
    updated_at                      TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

DOWNGRADE = """
DROP TABLE IF EXISTS org_calc_settings;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
