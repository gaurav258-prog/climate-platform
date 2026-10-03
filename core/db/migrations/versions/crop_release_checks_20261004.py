"""Every scheduled check of the publisher's file is recorded with what the publisher answered (E152).

The check compared the publisher's ETag / Last-Modified with the LAST RELEASE's — a release staged from a file on disk
has none, so every check downloaded the whole 34 MB file again (twice on 2026-10-04, during test-gate runs, staging
nothing because the file was unchanged). A check now records the validators it saw (and the file's sha-256 when it
downloaded), and the next check compares with that: an unchanged file costs one HEAD request.

  crop_release_checks   append-only: checked_at, source, last_modified, etag, changed, downloaded, file_sha256, outcome

Revision ID: crop_release_checks_20261004
Revises: crop_release_reader_20261004
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crop_release_checks_20261004"
down_revision: Union[str, None] = "crop_release_reader_20261004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO crop_release_checks (source, changed, downloaded, outcome) VALUES ('refusal probe', false, false, 'probe');""",
    "cleanup": """ALTER TABLE crop_release_checks DISABLE TRIGGER trg_crop_release_checks_append_only;
                   DELETE FROM crop_release_checks WHERE source = 'refusal probe';
                   ALTER TABLE crop_release_checks ENABLE TRIGGER trg_crop_release_checks_append_only;""",
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crop_release_checks (
            check_id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            checked_at    timestamptz NOT NULL DEFAULT now(),
            source        varchar(200) NOT NULL,
            last_modified text,
            etag          text,
            changed       boolean NOT NULL,
            downloaded    boolean NOT NULL,
            file_sha256   char(64),
            outcome       text NOT NULL,
            CHECK (downloaded OR file_sha256 IS NULL)
        );
        CREATE INDEX ix_crop_release_checks_source ON crop_release_checks (source, check_id DESC);
        CREATE FUNCTION prevent_crop_release_check_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'crop_release_checks is append-only: a check is what the publisher answered at the time';
        END $$;
        CREATE TRIGGER trg_crop_release_checks_append_only BEFORE UPDATE OR DELETE ON crop_release_checks
            FOR EACH ROW EXECUTE FUNCTION prevent_crop_release_check_mutation();
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM crop_release_checks) THEN
            RAISE EXCEPTION 'crop_release_checks_20261004 downgrade: checks are recorded — no table before this '
                            'revision keeps them';
          END IF;
        END $$;
        DROP TABLE crop_release_checks;
        DROP FUNCTION prevent_crop_release_check_mutation();
    """)
