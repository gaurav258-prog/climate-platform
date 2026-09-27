"""A reported company figure that is far from Tellumen's estimate, confirmed by a person as right.

When a company / vendor / manager figure differs from the sector or country estimate by more than a plausibility
band (energy intensity beyond 3× either way, an energy share more than 40 points apart), it is flagged: likely a unit
slip (MWh as GWh, a fraction as %). The manager corrects it — or confirms it here, with a reason. A confirmation is for
that exact value: if the figure changes, the check runs again. Append-only; audited.

Revision ID: data_confirmations_20260928
Revises: esg_energy_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "data_confirmations_20260928"
down_revision: Union[str, None] = "esg_energy_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS issuer_data_confirmations (
            confirmation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            issuer_id UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
            field TEXT NOT NULL,
            value NUMERIC NOT NULL,
            estimate NUMERIC,
            reason TEXT NOT NULL,
            confirmed_by UUID, confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_issuer_data_conf ON issuer_data_confirmations (org_id, issuer_id, field)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS issuer_data_confirmations")
