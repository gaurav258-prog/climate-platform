"""Customer data intake — drop-folder channels (the landing side of an SFTP feed).

  * intake_channels — one inbound folder per organisation + template, with an owner (the person who stands as the
    sender for 4-eyes) and optionally a pinned mapping. A sweep picks up each finished file and runs it through the
    same intake pipeline as an upload; the file is then moved to processed/ or refused/ (with the reason beside it).
  * intake_files.received_via now also allows 'sftp'.
The SFTP server itself (chrooted to these folders) is infrastructure: docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md #13.

Revision ID: intake_dropfolder_20260925
Revises: intake_autolayout_20260925
"""
from typing import Sequence, Union

from alembic import op

revision: str = "intake_dropfolder_20260925"
down_revision: Union[str, None] = "intake_autolayout_20260925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS intake_channels (
            channel_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id              UUID NOT NULL REFERENCES organizations(org_id),
            template            TEXT NOT NULL,
            kind                TEXT NOT NULL DEFAULT 'drop_folder',
            folder              TEXT NOT NULL UNIQUE,
            owner_user_id       UUID NOT NULL REFERENCES users(user_id),
            mapping_profile_id  UUID REFERENCES intake_mapping_profiles(profile_id),
            enabled             BOOLEAN NOT NULL DEFAULT TRUE,
            created_by          UUID REFERENCES users(user_id),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_swept_at       TIMESTAMPTZ,
            CONSTRAINT ck_channel_kind CHECK (kind IN ('drop_folder')),
            CONSTRAINT ux_channel_org_template UNIQUE (org_id, template, kind)
        )
    """)
    op.execute("ALTER TABLE ingest_batches ADD COLUMN IF NOT EXISTS channel_id UUID REFERENCES intake_channels(channel_id)")
    op.execute("ALTER TABLE intake_files DROP CONSTRAINT IF EXISTS ck_intake_file_via")
    op.execute("ALTER TABLE intake_files ADD CONSTRAINT ck_intake_file_via CHECK (received_via IN ('upload', 'api', 'sftp'))")


def downgrade() -> None:
    op.execute("ALTER TABLE intake_files DROP CONSTRAINT IF EXISTS ck_intake_file_via")
    op.execute("ALTER TABLE intake_files ADD CONSTRAINT ck_intake_file_via CHECK (received_via IN ('upload', 'api'))")
    op.execute("ALTER TABLE ingest_batches DROP COLUMN IF EXISTS channel_id")
    op.execute("DROP TABLE IF EXISTS intake_channels")
