"""CRCS record retention: how long each filed report must be kept, and a legal hold that stops archiving.

regulatory_filing.legal_hold / legal_hold_reason / legal_hold_since — set by a preparer, lifted only with a second
person (approval type filing.legal_hold_lift); every change is on the filing's event log.
reporting_entities.country — the country whose accounting law governs the entity's own records (blank = the
organisation's). The periods themselves are reference data (data/reference/retention/retention_rules.json).

Revision ID: retention_20260928
Revises: reg_act_relation_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "retention_20260928"
down_revision: Union[str, None] = "reg_act_relation_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE regulatory_filing ADD COLUMN IF NOT EXISTS legal_hold BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE regulatory_filing ADD COLUMN IF NOT EXISTS legal_hold_reason TEXT")
    op.execute("ALTER TABLE regulatory_filing ADD COLUMN IF NOT EXISTS legal_hold_since TIMESTAMPTZ")
    op.execute("ALTER TABLE reporting_entities ADD COLUMN IF NOT EXISTS country CHAR(2)")


def downgrade() -> None:
    op.execute("ALTER TABLE reporting_entities DROP COLUMN IF EXISTS country")
    for c in ("legal_hold_since", "legal_hold_reason", "legal_hold"):
        op.execute(f"ALTER TABLE regulatory_filing DROP COLUMN IF EXISTS {c}")
