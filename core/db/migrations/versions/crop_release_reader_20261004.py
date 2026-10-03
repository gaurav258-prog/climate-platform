"""A reference release is the publisher's file AS WE READ IT (E151).

The same FAOSTAT file read under different rules gives different rows: on 2026-10-04 the reading moved from a hand list
of 35 areas to every country (UN M49 = ISO numeric) and to the crop registry, so the July file — already landed —
yields more rows. A release identified by the file's sha-256 alone refused it as 'already recorded'. A release is now
identified by (source, file sha-256, reader): the reader is a fingerprint of the reading rules — the mapping files,
the country reference and the parser version — recorded with each release.

  crop_yield_releases.reader   text NOT NULL (releases before this revision: 'faostat-35-areas-v1')
  unique (source, file_sha256, reader)   replaces unique (source, file_sha256)

Downgrade refuses while two releases share a file (the old key cannot hold both).

Revision ID: crop_release_reader_20261004
Revises: approvers_required_20261004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crop_release_reader_20261004"
down_revision: Union[str, None] = "approvers_required_20261004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO crop_yield_releases (source, file_sha256, file_bytes, origin_url, summary, reader, status, decided_at)
                VALUES ('refusal probe', repeat('1', 64), 1, 'https://example.invalid/a', '{}', 'r1', 'rejected', now()),
                       ('refusal probe', repeat('1', 64), 1, 'https://example.invalid/b', '{}', 'r2', 'rejected', now());""",
    "cleanup": """DELETE FROM crop_yield_releases WHERE source = 'refusal probe';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE crop_yield_releases ADD COLUMN reader text;
        UPDATE crop_yield_releases SET reader = 'faostat-35-areas-v1';
        ALTER TABLE crop_yield_releases ALTER COLUMN reader SET NOT NULL;
        DROP INDEX ux_crop_release_file;
        CREATE UNIQUE INDEX ux_crop_release_file ON crop_yield_releases (source, file_sha256, reader);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM crop_yield_releases GROUP BY source, file_sha256 HAVING count(*) > 1) THEN
            RAISE EXCEPTION 'crop_release_reader_20261004 downgrade: a file is recorded under two readers — the key '
                            'before this revision cannot hold both';
          END IF;
        END $$;
        DROP INDEX ux_crop_release_file;
        CREATE UNIQUE INDEX ux_crop_release_file ON crop_yield_releases (source, file_sha256);
        ALTER TABLE crop_yield_releases DROP COLUMN reader;
    """)
