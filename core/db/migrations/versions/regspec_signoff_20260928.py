"""Regulatory specifications: four-eyes sign-off of each spec file's exact bytes.

regspec_signoff  one row per sign-off: framework, version, the sha256 of the file the signer reviewed, the role
                 (regulatory reviewer / engineer) and who. Append-only. The same person can sign a given file once,
                 so two roles means two people; a sign-off on an older sha no longer counts once the file changes.

Revision ID: regspec_signoff_20260928
Revises: reg_early_signal_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "regspec_signoff_20260928"
down_revision: Union[str, None] = "reg_early_signal_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS regspec_signoff (
            signoff_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            framework   TEXT NOT NULL,
            version     TEXT NOT NULL,
            sha256      CHAR(64) NOT NULL,
            role        TEXT NOT NULL CONSTRAINT ck_regspec_signoff_role CHECK (role IN ('regulatory', 'engineering')),
            user_id     UUID NOT NULL REFERENCES users(user_id),
            note        TEXT,
            signed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_regspec_signoff_role ON regspec_signoff (framework, version, sha256, role)")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_regspec_signoff_person ON regspec_signoff (framework, version, sha256, user_id)")
    op.execute("""
        CREATE OR REPLACE FUNCTION regspec_signoff_append_only() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'regspec_signoff is append-only'; END; $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS tr_regspec_signoff_worm ON regspec_signoff")
    op.execute("""CREATE TRIGGER tr_regspec_signoff_worm BEFORE UPDATE OR DELETE ON regspec_signoff
                  FOR EACH ROW EXECUTE FUNCTION regspec_signoff_append_only()""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regspec_signoff")
    op.execute("DROP FUNCTION IF EXISTS regspec_signoff_append_only()")
