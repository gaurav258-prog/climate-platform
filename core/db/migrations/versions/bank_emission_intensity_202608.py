"""ext_banking.emission_intensity — per-counterparty physical carbon intensity in the IEA sectoral unit.

The Pillar 3 / EBA transition Template 3 (IEA-alignment) needs each counterparty's PHYSICAL emission intensity
in the IEA metric's own unit (gCO2/kWh for power, tCO2/t for steel/cement, …) to compute the portfolio's
distance to the IEA 2030 pathway. This is NOT the financial carbon intensity (tCO2e/€M revenue, already on the
table) — a different quantity in a different unit, so it is a distinct customer-supplied per-loan attribute the
buyer uploads with the rest of their book. Nullable; where absent, Template 3 keeps the alignment distance
'pending' rather than inventing one. See services/governance/transition_alignment.py.

Revision ID: bank_emission_intensity_202608
Revises: bank_loan_attributes_202608
"""
from alembic import op

revision = "bank_emission_intensity_202608"
down_revision = "bank_loan_attributes_202608"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE ext_banking ADD COLUMN IF NOT EXISTS emission_intensity DOUBLE PRECISION")


def downgrade() -> None:
    op.execute("ALTER TABLE ext_banking DROP COLUMN IF EXISTS emission_intensity")
