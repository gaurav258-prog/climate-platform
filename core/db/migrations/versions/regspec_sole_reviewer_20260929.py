"""Spec sign-off by a sole reviewer, declared as such.

A team of one cannot give two people's sign-off. The same person may sign both roles only by declaring it
(sole_reviewer); the record then says 'signed off by one person' instead of passing for a four-eyes review. The
per-person unique index now applies only to undeclared sign-offs, so the database still refuses a silent second
signature by the same person.

Revision ID: regspec_sole_reviewer_20260929
Revises: bank_p3_attributes_20260928
"""
from typing import Sequence, Union

from alembic import op

revision: str = "regspec_sole_reviewer_20260929"
down_revision: Union[str, None] = "bank_p3_attributes_20260928"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE regspec_signoff ADD COLUMN IF NOT EXISTS sole_reviewer BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("DROP INDEX IF EXISTS ux_regspec_signoff_person")
    op.execute("""CREATE UNIQUE INDEX ux_regspec_signoff_person ON regspec_signoff (framework, version, sha256, user_id)
                  WHERE NOT sole_reviewer""")
    op.execute("""ALTER TABLE regspec_signoff ADD CONSTRAINT ck_regspec_sole_reviewer_note
                  CHECK (NOT sole_reviewer OR coalesce(length(trim(note)), 0) > 0)""")


def downgrade() -> None:
    op.execute("ALTER TABLE regspec_signoff DROP CONSTRAINT IF EXISTS ck_regspec_sole_reviewer_note")
    op.execute("DROP INDEX IF EXISTS ux_regspec_signoff_person")
    op.execute("CREATE UNIQUE INDEX ux_regspec_signoff_person ON regspec_signoff (framework, version, sha256, user_id)")
    op.execute("ALTER TABLE regspec_signoff DROP COLUMN IF EXISTS sole_reviewer")
