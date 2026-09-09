"""supervision_evidence_pack — immutable, versioned case files a supervisor generates for one entity.

Each pack is the assembled content (JSON) plus its rendered PDF, hashed; rows are never updated. A new
generation is a new version.

Revision ID: sup_evidence_20260909
Revises: sup_geo_prior_20260908
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_evidence_20260909"
down_revision: Union[str, None] = "sup_geo_prior_20260908"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_evidence_pack (
            pack_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regulator_org_id   UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            supervised_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            version            INTEGER NOT NULL,
            basis              JSONB NOT NULL,
            content            JSONB NOT NULL,
            sha256             TEXT NOT NULL,
            pdf                BYTEA NOT NULL,
            pdf_bytes          INTEGER NOT NULL,
            note               TEXT,
            generated_by       UUID REFERENCES users(user_id),
            generated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (regulator_org_id, supervised_org_id, version)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sup_evidence_entity ON supervision_evidence_pack (regulator_org_id, supervised_org_id, version DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervision_evidence_pack")
