"""issuer_esg_metrics — the non-carbon PAI inputs (energy/water/waste/social)

Revision ID: esg_metrics_20260712
Revises: c2d3e4f5a6b7
Create Date: 2026-07-12

The SFDR PAI statement has 14 mandatory investee indicators. Four are carbon
(computed from emissions we already hold). The other ten are NOT derivable from
carbon or location data — they are per-issuer ESG facts a manager gets from its
ESG data feed:

  PAI 5   non-renewable energy consumption/production share (%)
  PAI 6   energy consumption intensity (GWh per €M revenue)
  PAI 7   operations in/near biodiversity-sensitive areas (flag)
  PAI 8   emissions to water (tonnes)
  PAI 9   hazardous & radioactive waste (tonnes)
  PAI 10  UN Global Compact / OECD Guidelines violations (flag)
  PAI 11  lacks processes to monitor UNGC/OECD compliance (flag)
  PAI 12  unadjusted gender pay gap (%)
  PAI 13  board gender diversity — female share (%)
  PAI 14  involvement in controversial weapons (flag)

Like emissions, this is a private per-org disclosure (two managers may hold the
same issuer with different vendor data), so it is org-scoped: org_id set = that
org's disclosure. Nothing here is fabricated — an issuer with no ESG row simply
leaves those indicators as disclosed gaps.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "esg_metrics_20260712"
down_revision: Union[str, None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE issuer_esg_metrics (
    esg_id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issuer_id                  UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
    org_id                     UUID REFERENCES organizations(org_id) ON DELETE CASCADE,
    reporting_year             INTEGER NOT NULL,
    -- PAI 5-6 energy
    non_renewable_energy_pct   NUMERIC(6,3),
    energy_intensity_gwh_per_meur NUMERIC(12,4),
    -- PAI 7-9 environment
    biodiversity_sensitive_ops BOOLEAN,
    emissions_to_water_tonnes  NUMERIC(20,2),
    hazardous_waste_tonnes     NUMERIC(20,2),
    -- PAI 10-14 social & governance
    ungc_oecd_violation        BOOLEAN,
    ungc_oecd_no_monitoring    BOOLEAN,
    gender_pay_gap_pct         NUMERIC(6,3),
    board_female_pct           NUMERIC(6,3),
    controversial_weapons      BOOLEAN,
    source                     VARCHAR(20) NOT NULL DEFAULT 'client'
                               CHECK (source IN ('client','vendor','disclosed')),
    data_vintage               DATE,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_esg_issuer ON issuer_esg_metrics(issuer_id);
-- one row per issuer/year/org (org-scoped private disclosure); one global row (org NULL).
CREATE UNIQUE INDEX ux_esg_org ON issuer_esg_metrics(issuer_id, reporting_year) WHERE org_id IS NULL;
CREATE UNIQUE INDEX ux_esg_org_scoped ON issuer_esg_metrics(issuer_id, reporting_year, org_id) WHERE org_id IS NOT NULL;
"""

DOWNGRADE = "DROP TABLE IF EXISTS issuer_esg_metrics;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
