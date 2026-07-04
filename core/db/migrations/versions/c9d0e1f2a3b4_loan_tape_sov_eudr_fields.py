"""loan_tape_sov_eudr_fields

Grounds each vertical's input schema in the real industry-standard format that
sector already exchanges this data in, instead of the ad-hoc demo columns the
upload feature shipped with. All new columns are nullable -- existing rows and
the CSV upload path both keep working unchanged; these fields only light up
when a real counterparty's template supplies them.

- bank_assets: outstanding_loan_balance_eur + loan_origination_date -- a real
  "loan tape" needs the loan side of the picture, not just collateral value.
  Enables LTV / climate-adjusted LTV (ml/scoring/valuation_discount.py).
- insurance_policies: building/contents/business-interruption value +
  construction_type (ISO Classes 1-5) + year_built + number_of_stories -- the
  real Statement of Values (SOV, ACORD 140) fields, replacing a single lump
  sum_insured_eur with a genuine TIV breakdown.
- sc_sourcing_plots: plot_area_ha -- EUDR's own >4ha/<=4ha polygon-vs-point
  threshold, a real due-diligence-statement field.

Revision ID: c9d0e1f2a3b4
Revises: b2c3d4e5f6a7
Create Date: 2026-07-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
ALTER TABLE bank_assets
    ADD COLUMN IF NOT EXISTS outstanding_loan_balance_eur NUMERIC(18,2),
    ADD COLUMN IF NOT EXISTS loan_origination_date DATE;

ALTER TABLE insurance_policies
    ADD COLUMN IF NOT EXISTS building_value_eur NUMERIC(16,2),
    ADD COLUMN IF NOT EXISTS contents_value_eur NUMERIC(16,2),
    ADD COLUMN IF NOT EXISTS business_interruption_value_eur NUMERIC(16,2),
    ADD COLUMN IF NOT EXISTS construction_type VARCHAR(30),
    ADD COLUMN IF NOT EXISTS year_built INTEGER,
    ADD COLUMN IF NOT EXISTS number_of_stories INTEGER;

ALTER TABLE insurance_policies
    DROP CONSTRAINT IF EXISTS insurance_policies_construction_type_chk;
ALTER TABLE insurance_policies
    ADD CONSTRAINT insurance_policies_construction_type_chk
    CHECK (construction_type IS NULL OR construction_type IN
        ('frame', 'joisted_masonry', 'non_combustible', 'masonry_non_combustible', 'fire_resistive'));

ALTER TABLE sc_sourcing_plots
    ADD COLUMN IF NOT EXISTS plot_area_ha NUMERIC(10,2);
"""

DOWNGRADE = """
ALTER TABLE sc_sourcing_plots DROP COLUMN IF EXISTS plot_area_ha;

ALTER TABLE insurance_policies DROP CONSTRAINT IF EXISTS insurance_policies_construction_type_chk;
ALTER TABLE insurance_policies
    DROP COLUMN IF EXISTS building_value_eur,
    DROP COLUMN IF EXISTS contents_value_eur,
    DROP COLUMN IF EXISTS business_interruption_value_eur,
    DROP COLUMN IF EXISTS construction_type,
    DROP COLUMN IF EXISTS year_built,
    DROP COLUMN IF EXISTS number_of_stories;

ALTER TABLE bank_assets
    DROP COLUMN IF EXISTS outstanding_loan_balance_eur,
    DROP COLUMN IF EXISTS loan_origination_date;
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
