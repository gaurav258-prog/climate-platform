"""Customer data intake — automatic layouts: a saved mapping remembers the column layout it was built for.

  * intake_mapping_profiles.source_fingerprint — a hash of the source file's column names (case / spacing /
    order-insensitive). A later file with the same fingerprint is read through the latest confirmed version of that
    mapping without the customer choosing it; a file whose columns changed is asked about again.

Revision ID: intake_autolayout_20260925
Revises: intake_staging_20260925
"""
from typing import Sequence, Union

from alembic import op

revision: str = "intake_autolayout_20260925"
down_revision: Union[str, None] = "intake_staging_20260925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE intake_mapping_profiles ADD COLUMN IF NOT EXISTS source_fingerprint TEXT")
    op.execute("ALTER TABLE intake_mapping_profiles ADD COLUMN IF NOT EXISTS source_columns JSONB")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mapping_profile_fp ON intake_mapping_profiles (org_id, template, source_fingerprint)
                  WHERE source_fingerprint IS NOT NULL""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_mapping_profile_fp")
    op.execute("ALTER TABLE intake_mapping_profiles DROP COLUMN IF EXISTS source_columns, DROP COLUMN IF EXISTS source_fingerprint")
