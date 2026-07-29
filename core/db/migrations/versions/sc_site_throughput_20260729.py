"""Add sc_company_sites.annual_throughput_eur — revenue/goods flowing through a site, for
business-interruption exposure (distinct from asset value, which is damage exposure).

annual_value_eur  = what's DAMAGED if a hazard hits (PP&E + inventory) → value-at-risk.
annual_throughput_eur = what STOPS FLOWING if the site goes down (revenue/goods per year) →
                        business-interruption exposure (downtime × daily throughput).

Revision ID: sc_site_throughput_20260729
Revises: sc_company_sites_20260729
"""
import sqlalchemy as sa
from alembic import op

revision = "sc_site_throughput_20260729"
down_revision = "sc_company_sites_20260729"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sc_company_sites", sa.Column("annual_throughput_eur", sa.Numeric(), nullable=True))


def downgrade() -> None:
    op.drop_column("sc_company_sites", "annual_throughput_eur")
