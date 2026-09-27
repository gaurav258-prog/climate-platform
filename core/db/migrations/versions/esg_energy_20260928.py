"""Company energy facts for SFDR PAI 5 and 6, as the European ESG Template asks for them.

  * energy_consumption_gwh          the company's total energy consumption (ESRS E1-5) — intensity per sector is
                                    derived from it and the company's revenue when no intensity is given
  * non_renewable_consumption_pct   share of its energy CONSUMPTION from non-renewable sources (EET 30420)
  * non_renewable_production_pct    share of its energy PRODUCTION from non-renewable sources (EET 30460; producers)
non_renewable_energy_pct stays: the combined RTS PAI 5 figure when that is all a source gives.

Revision ID: esg_energy_20260928
Revises: eet_20260927
"""
from typing import Sequence, Union

from alembic import op

revision: str = "esg_energy_20260928"
down_revision: Union[str, None] = "eet_20260927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE issuer_esg_metrics ADD COLUMN IF NOT EXISTS energy_consumption_gwh NUMERIC(20,4)")
    op.execute("ALTER TABLE issuer_esg_metrics ADD COLUMN IF NOT EXISTS non_renewable_consumption_pct NUMERIC(6,3)")
    op.execute("ALTER TABLE issuer_esg_metrics ADD COLUMN IF NOT EXISTS non_renewable_production_pct NUMERIC(6,3)")


def downgrade() -> None:
    for c in ("non_renewable_production_pct", "non_renewable_consumption_pct", "energy_consumption_gwh"):
        op.execute(f"ALTER TABLE issuer_esg_metrics DROP COLUMN IF EXISTS {c}")
