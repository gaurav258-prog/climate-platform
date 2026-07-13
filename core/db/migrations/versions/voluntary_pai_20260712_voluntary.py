"""Voluntary (additional) PAI — per-fund selection + per-issuer values

Revision ID: voluntary_pai_20260712
Revises: dnsh_flags_20260712
Create Date: 2026-07-12

SFDR requires a manager to adopt AT LEAST ONE additional climate/environmental
indicator (RTS Annex I, Table 2) and AT LEAST ONE additional social indicator
(Table 3), on top of the 14 mandatory ones. Which ones is the manager's choice.

Two org-scoped tables:
  * fund_voluntary_pai  — the indicators a fund has ADOPTED (the manager's choice)
  * issuer_voluntary_pai — the per-issuer values for those indicators (numeric or
                           boolean), the manager's private disclosure

The fund figure is computed (value-weighted for numeric, share-of-value for
boolean) over holdings that supplied data — coverage disclosed, never fabricated.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "voluntary_pai_20260712"
down_revision: Union[str, None] = "dnsh_flags_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE fund_voluntary_pai (
            fund_id        UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
            org_id         UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            indicator_key  VARCHAR(60) NOT NULL,   -- key into the code-side catalog
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (fund_id, indicator_key)
        );

        CREATE TABLE issuer_voluntary_pai (
            issuer_id      UUID NOT NULL REFERENCES issuers(issuer_id) ON DELETE CASCADE,
            org_id         UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            indicator_key  VARCHAR(60) NOT NULL,
            reporting_year INT NOT NULL,
            value_num      NUMERIC(20,4),          -- for numeric indicators
            value_bool     BOOLEAN,                -- for yes/no indicators
            source         VARCHAR(20) NOT NULL DEFAULT 'client',
            data_vintage   TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (issuer_id, org_id, indicator_key, reporting_year)
        );
        CREATE INDEX ix_issuer_voluntary_pai_key ON issuer_voluntary_pai(indicator_key);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS issuer_voluntary_pai;
        DROP TABLE IF EXISTS fund_voluntary_pai;
    """)
