"""Regulatory mandate registry support: entity regulatory attributes, per-supervisor mandate settings, version acknowledgements.

Revision ID: sup_mandates_20260909
Revises: sup_evidence_20260909
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_mandates_20260909"
down_revision: Union[str, None] = "sup_evidence_20260909"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS org_regulatory_attribute (
            org_id      UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            attribute   TEXT NOT NULL,
            value_num   DOUBLE PRECISION,
            value_text  TEXT,
            value_bool  BOOLEAN,
            as_of       DATE,
            source      TEXT NOT NULL DEFAULT 'entity',   -- entity | supervisor | registry
            updated_by  UUID,
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, attribute)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_mandate_setting (
            regulator_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            mandate_id        TEXT NOT NULL,
            enabled           BOOLEAN NOT NULL DEFAULT TRUE,
            overrides         JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {"criteria": {...}, "due": {...}} per authority
            note              TEXT,
            updated_by        UUID,
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (regulator_org_id, mandate_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_mandate_version_ack (
            regulator_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            mandate_id        TEXT NOT NULL,
            version           TEXT NOT NULL,
            acknowledged_by   UUID,
            acknowledged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            note              TEXT,
            PRIMARY KEY (regulator_org_id, mandate_id, version)
        )
    """)
    op.execute("INSERT INTO permissions (code, description) VALUES ('supervisor.mandates.manage', "
               "'Enable, adapt and acknowledge regulatory mandates for this authority') ON CONFLICT (code) DO NOTHING")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervisor_mandate_version_ack")
    op.execute("DROP TABLE IF EXISTS supervisor_mandate_setting")
    op.execute("DROP TABLE IF EXISTS org_regulatory_attribute")
