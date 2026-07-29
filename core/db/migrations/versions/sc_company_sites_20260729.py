"""Add sc_company_sites — a food/agri company's OWN operational sites (HQ, plants, warehouses, DCs).

Base-coverage build, step 1. Until now the agri workspace modelled only the SUPPLY side
(sc_sourcing_plots — farms/suppliers). A prospect's own climate exposure is also its own
operations: head office, factories, cold stores, distribution centres. This table holds those
sites the same way sc_sourcing_plots holds suppliers — a point (lat/lon) snapped to the H3 res-8
grid, scored against the golden source via the shared on-demand scorer, with geocode provenance.
A companion view v_sc_site_physical_risk projects canonical_scores onto each site's cell, exactly
mirroring v_sc_plot_physical_risk, so sites and suppliers run through one scoring path, not two.

Revision ID: sc_company_sites_20260729
Revises: eudr_dds_20260727
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "sc_company_sites_20260729"
down_revision = "eudr_dds_20260727"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sc_company_sites",
        sa.Column("site_id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(), nullable=False),
        # hq | factory | warehouse | distribution_centre | office | other
        sa.Column("site_type", sa.String(), nullable=False, server_default="other"),
        sa.Column("address", sa.String(), nullable=True),          # raw address as entered (provenance)
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("h3_cell", sa.String(), nullable=True),          # res-8 key into canonical_scores
        sa.Column("country", sa.String(), nullable=True),
        sa.Column("region", sa.String(), nullable=True),
        sa.Column("annual_value_eur", sa.Numeric(), nullable=True),  # asset value / throughput → value-at-risk
        sa.Column("confidence", sa.Numeric(), nullable=True),        # geocode confidence (street>city>country)
        sa.Column("geocode_precision", sa.String(), nullable=True),  # street | city | country | exact
        sa.Column("source", sa.String(), nullable=True),            # 'user_upload' | 'user_entry' | ...
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Per-site per-hazard physical risk — mirror of v_sc_plot_physical_risk (standing lane, current head).
    op.execute("""
        CREATE OR REPLACE VIEW v_sc_site_physical_risk AS
        SELECT s.org_id, s.site_id, s.h3_cell, s.site_type, s.name,
               s.annual_value_eur,
               cs.hazard_type,
               cs.risk_score::double precision AS physical_risk_score,
               cs.scenario, cs.time_horizon, cs.model_version, cs.scored_at
        FROM sc_company_sites s
        JOIN canonical_scores cs
          ON cs.h3_cell = s.h3_cell AND cs.valid_to IS NULL AND cs.score_lane = 'standing';
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_sc_site_physical_risk")
    op.drop_table("sc_company_sites")
