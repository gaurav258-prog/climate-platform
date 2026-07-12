"""issuer_evic — enterprise value incl. cash, for PCAF financed emissions

Revision ID: c2d3e4f5a6b7
Revises: b0c1d2e3f4a5
Create Date: 2026-07-12

SFDR PAI 1 (financed GHG emissions) and PAI 2 (carbon footprint) are the two
headline carbon figures a manager files. Both need each issuer's EVIC —
Enterprise Value Including Cash — as the PCAF attribution denominator:

    attribution_factor  =  investment (market value)  ÷  EVIC
    financed_emissions  =  Σ  attribution_factor × investee GHG (scope 1/2/3)

EVIC is issuer financial data that varies by year and source, exactly like the
revenue we already store, so it lives on issuer_emissions (per issuer / year /
source / org). A manager typically has EVIC in their own data terminal and
supplies it; where absent, PAI 1/2 stay honestly gap-flagged (not fabricated).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE issuer_emissions ADD COLUMN evic_eur NUMERIC(20,2)")


def downgrade() -> None:
    op.execute("ALTER TABLE issuer_emissions DROP COLUMN IF EXISTS evic_eur")
