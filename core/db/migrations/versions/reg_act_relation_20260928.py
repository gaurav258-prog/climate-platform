"""CRCS version pinning: which acts amend or replace each act a framework is filed under — live from the EU register.

reg_act_relation   one row per (governing act, related act, relation): amends | repeals | implicitly_repeals, with the
                   related act's English title, entry-into-force dates and in-force flag as the register gives them.
                   Refreshed by the daily scan; a relation seen for the first time is also a detected change.

Revision ID: reg_act_relation_20260928
Revises: crcs_legacy_retire_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "reg_act_relation_20260928"
down_revision: Union[str, None] = "crcs_legacy_retire_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS reg_act_relation (
            celex           TEXT NOT NULL,
            related_celex   TEXT NOT NULL,
            relation        TEXT NOT NULL CONSTRAINT ck_reg_act_relation CHECK (relation IN ('amends', 'repeals', 'implicitly_repeals')),
            title           TEXT,
            entry_into_force JSONB NOT NULL DEFAULT '[]'::jsonb,
            in_force        BOOLEAN,
            first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (celex, related_celex, relation)
        )""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reg_act_relation")
