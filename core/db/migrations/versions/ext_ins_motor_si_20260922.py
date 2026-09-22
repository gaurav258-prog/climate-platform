"""Add motor_sum_insured_eur to ext_insurance — Art. 123(7)/124(7) flood/hail motor-vehicle sum insured
component of the Solvency II standard-formula NatCat SCR (services/governance/solvency2_natcat.py already
reads pol.get("motor_sum_insured_eur"); this was dead code from the UI's perspective until now). Nullable —
absent on a pure property book (LoB 6/7/18/19), which then computes the motor term as 0.

Revision ID: ext_ins_motor_si_20260922
Revises: reit_gross_revenue_20260922
"""
import sqlalchemy as sa
from alembic import op

revision = "ext_ins_motor_si_20260922"
down_revision = "reit_gross_revenue_20260922"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ext_insurance") as b:
        b.add_column(sa.Column("motor_sum_insured_eur", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ext_insurance") as b:
        b.drop_column("motor_sum_insured_eur")
