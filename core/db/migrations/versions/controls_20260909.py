"""Reporting control register — every automated reporting check named as a control, its test runs and outcomes,
and its owner.

Revision ID: controls_20260909
Revises: board_pack_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "controls_20260909"
down_revision: Union[str, None] = "board_pack_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS control_test_run (
            run_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id        UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            trigger       TEXT NOT NULL,                -- sweep | manual
            actor_user_id UUID REFERENCES users(user_id),
            n_controls    INTEGER NOT NULL,
            n_pass        INTEGER NOT NULL,
            n_fail        INTEGER NOT NULL,
            n_na          INTEGER NOT NULL,
            register_version TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_control_run_org ON control_test_run (org_id, at DESC);
        CREATE TABLE IF NOT EXISTS control_test_result (
            result_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id     UUID NOT NULL REFERENCES control_test_run(run_id) ON DELETE CASCADE,
            org_id     UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            control_id TEXT NOT NULL,
            outcome    TEXT NOT NULL,                   -- pass | fail | not_applicable
            n_items    INTEGER NOT NULL DEFAULT 0,
            n_failed   INTEGER NOT NULL DEFAULT 0,
            detail     JSONB NOT NULL DEFAULT '[]'::jsonb,
            at         TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS ix_control_result ON control_test_result (org_id, control_id, at DESC);
        CREATE TABLE IF NOT EXISTS control_owner (
            org_id        UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            control_id    TEXT NOT NULL,
            owner_user_id UUID REFERENCES users(user_id),
            review_by     DATE,
            note          TEXT,
            updated_by    UUID REFERENCES users(user_id),
            updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, control_id)
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS control_owner; DROP TABLE IF EXISTS control_test_result; DROP TABLE IF EXISTS control_test_run;")
