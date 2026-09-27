"""European ESG Template (EET): share classes, the manager's own answers, and published EET versions.

  * fund_share_classes — the versions of a fund sold to investors (own ISIN, currency, hedged, distribution policy).
    The EET is one row per share class; a held ISIN that is one of the organisation's own classes resolves to its fund.
  * org_eet_answers / fund_eet_answers — what the manager states (manufacturer-level fields once for the
    organisation; product fields per fund) that Tellumen cannot compute (commitments, minimum proportions,
    exclusions, links to disclosures): one value per field, checked against the field's format.
  * eet_publications — an EET version as prepared (frozen payload + completeness + sha256), which a SECOND person
    must approve before it is published and can be sent to distributors. Append-only: the payload can never change;
    status moves only pending → published | rejected.

Revision ID: eet_20260927
Revises: fund_native_value_20260927
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eet_20260927"
down_revision: Union[str, None] = "fund_native_value_20260927"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS fund_share_classes (
            share_class_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            fund_id UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
            isin CHAR(12) NOT NULL,
            name TEXT NOT NULL,
            currency CHAR(3) NOT NULL,
            hedged BOOLEAN NOT NULL DEFAULT false,
            distribution TEXT NOT NULL CHECK (distribution IN ('accumulating', 'distributing')),
            launch_date DATE,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
            created_by UUID, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by UUID, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (org_id, isin)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fund_share_classes_fund ON fund_share_classes (fund_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS fund_eet_answers (
            fund_id UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_by UUID, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (fund_id, field_name)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS org_eet_answers (
            org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            field_name TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_by UUID, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, field_name)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS eet_publications (
            publication_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            version INTEGER NOT NULL,
            eet_version TEXT NOT NULL,
            uses JSONB NOT NULL,
            reference_date DATE NOT NULL,
            payload JSONB NOT NULL,
            completeness JSONB NOT NULL,
            payload_sha256 TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'published', 'rejected')),
            prepared_by UUID, prepared_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            approval_request_id UUID,
            decided_by UUID, decided_at TIMESTAMPTZ, decision_reason TEXT,
            UNIQUE (org_id, version)
        )
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION eet_publications_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'eet_publications is append-only: a published EET is never deleted';
            END IF;
            IF NEW.payload IS DISTINCT FROM OLD.payload OR NEW.payload_sha256 IS DISTINCT FROM OLD.payload_sha256
               OR NEW.completeness IS DISTINCT FROM OLD.completeness OR NEW.version IS DISTINCT FROM OLD.version
               OR NEW.org_id IS DISTINCT FROM OLD.org_id OR NEW.prepared_by IS DISTINCT FROM OLD.prepared_by THEN
                RAISE EXCEPTION 'eet_publications is append-only: a prepared EET version never changes';
            END IF;
            IF OLD.status <> 'pending' AND NEW.status IS DISTINCT FROM OLD.status THEN
                RAISE EXCEPTION 'eet_publications: a % EET version cannot change status', OLD.status;
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_eet_publications_guard BEFORE UPDATE OR DELETE ON eet_publications
        FOR EACH ROW EXECUTE FUNCTION eet_publications_guard()
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS eet_publications")
    op.execute("DROP FUNCTION IF EXISTS eet_publications_guard()")
    op.execute("DROP TABLE IF EXISTS org_eet_answers")
    op.execute("DROP TABLE IF EXISTS fund_eet_answers")
    op.execute("DROP TABLE IF EXISTS fund_share_classes")
