"""Add cresta_zone to ext_insurance — the EIOPA risk zone per insured location, for the exact Solvency II
standard-formula zonal SCR (Del. Reg. 2015/35, Annex IX). A Statement of Values normally already carries the
postcode / CRESTA zone per risk; the standard-formula calc aggregates sum insured by that zone. Nullable —
absent on a coordinate-only book, which then uses the country-level approximation.

Revision ID: ext_ins_cresta_zone_20260906
Revises: regulator_supervision_20260906
"""
import sqlalchemy as sa
from alembic import op

revision = "ext_ins_cresta_zone_20260906"
down_revision = "regulator_supervision_20260906"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ext_insurance") as b:
        b.add_column(sa.Column("cresta_zone", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ext_insurance") as b:
        b.drop_column("cresta_zone")
