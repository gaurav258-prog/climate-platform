"""supply_model_validation

Persist the agriculture impact-function BACKTESTS so the validation that makes the euro
figures credible (cocoa=heat reproduces −12.9%; coffee=drought reproduces −12.7%) lives in
the product, not just in script stdout. One row per event; written by
scripts/record_ag_validation.py from the existing scripts/backtest_*.py findings.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-02
"""
from typing import Sequence, Union
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UPGRADE = """
CREATE TABLE IF NOT EXISTS sc_model_validation (
    validation_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event                   VARCHAR(80) NOT NULL,       -- 'Cocoa 2023/24'
    commodity               VARCHAR(80) NOT NULL,
    hazard                  VARCHAR(40) NOT NULL,       -- validated driver (heat_acute, drought)
    observed_prod_shock_pct NUMERIC(8,2),               -- realised production shock (ground truth)
    model_price_move_pct    NUMERIC(8,2),               -- model's price move (reproduced)
    observed_price_move_pct NUMERIC(8,2),               -- realised price move
    skill_note              TEXT NOT NULL,              -- the honest finding + limits
    source                  VARCHAR(200) NOT NULL,
    run_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (event)
);
"""
DOWNGRADE = "DROP TABLE IF EXISTS sc_model_validation;"


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
