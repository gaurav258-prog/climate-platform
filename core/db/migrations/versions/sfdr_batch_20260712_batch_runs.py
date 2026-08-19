"""SFDR batch runs — orchestrate statement generation across many funds

Revision ID: sfdr_batch_20260712
Revises: voluntary_pai_20260712
Create Date: 2026-07-12

A manager with hundreds of funds files on one annual cycle (reference period ends
31 Dec, filing due 30 Jun). Rather than generate each statement by hand, a BATCH
enumerates all the manager's funds, computes each statement, and records per-fund
status + readiness. The run is RESUMABLE — re-running processes only the funds not
yet done, so a crash or a rate-limit mid-run doesn't lose progress.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sfdr_batch_20260712"
down_revision: Union[str, None] = "voluntary_pai_20260712"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sfdr_batch_runs (
            batch_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id         UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            reference_year INT NOT NULL,
            status         VARCHAR(12) NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending','running','completed','failed')),
            total_funds    INT NOT NULL DEFAULT 0,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_sfdr_batch_runs_org ON sfdr_batch_runs(org_id);

        CREATE TABLE sfdr_batch_items (
            batch_id       UUID NOT NULL REFERENCES sfdr_batch_runs(batch_id) ON DELETE CASCADE,
            fund_id        UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
            fund_name      VARCHAR(200),
            status         VARCHAR(12) NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending','running','done','error')),
            computed       INT,
            partial        INT,
            not_available  INT,
            ready_to_file  BOOLEAN,
            error          TEXT,
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (batch_id, fund_id)
        );
        CREATE INDEX ix_sfdr_batch_items_status ON sfdr_batch_items(batch_id, status);
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS sfdr_batch_items;
        DROP TABLE IF EXISTS sfdr_batch_runs;
    """)
