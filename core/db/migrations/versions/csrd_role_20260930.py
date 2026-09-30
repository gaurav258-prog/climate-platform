"""Who reports, in which role, for which financial year — and the carrying amount addressed by adaptation actions.

csrd_reporting_role   per undertaking (NULL = the organisation itself) and financial year (period_end): individual
                      (Directive 2013/34/EU Art. 19a), consolidated (Art. 29a, the parent of the group), exempt
                      subsidiary (Art. 19a(9) / 29a(8): included in a parent's consolidated report — whose name,
                      registered office and report are stated), or voluntary. Requested by one person, applied when a
                      second approves; append-only, the latest statement is the live role.
site_period_values    measure 'carrying_amount_adapted': the part of a site's carrying amount addressed by adaptation
                      actions at the period end (ESRS E1 (2023) §66(b), (2026) §39(b)) — at most its carrying amount.

Revision ID: csrd_role_20260930
Revises: provided_money_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "csrd_role_20260930"
down_revision: Union[str, None] = "provided_money_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000feea"
_U1, _U2 = "0bbe0bbe-0000-4000-8000-00000000fe01", "0bbe0bbe-0000-4000-8000-00000000fe02"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'manufacturer', 'ES');
                 INSERT INTO csrd_reporting_role (org_id, period_end, role, requested_by, approved_by)
                 VALUES ('{_PROBE_ORG}', '2025-12-31', 'individual', '{_U1}', '{_U2}');""",
    "cleanup": f"""ALTER TABLE csrd_reporting_role DISABLE TRIGGER trg_csrd_role_worm;
                   DELETE FROM csrd_reporting_role WHERE org_id = '{_PROBE_ORG}';
                   ALTER TABLE csrd_reporting_role ENABLE TRIGGER trg_csrd_role_worm;
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE csrd_reporting_role (
            role_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                  BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
            org_id               UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            reporting_entity_id  UUID REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
            period_end           DATE NOT NULL,
            role                 TEXT NOT NULL CONSTRAINT ck_csrd_role
                                 CHECK (role IN ('individual', 'consolidated', 'exempt_subsidiary', 'voluntary')),
            parent_name          TEXT,
            parent_registered_office TEXT,
            parent_report_ref    TEXT,
            basis                TEXT,
            requested_by         UUID NOT NULL,
            approved_by          UUID NOT NULL,
            approval_request_id  UUID,
            recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_csrd_role_four_eyes CHECK (requested_by <> approved_by),
            CONSTRAINT ck_csrd_role_exempt_parent CHECK (role <> 'exempt_subsidiary' OR
                (parent_name IS NOT NULL AND parent_registered_office IS NOT NULL AND parent_report_ref IS NOT NULL))
        );
        CREATE INDEX ix_csrd_role ON csrd_reporting_role (org_id, reporting_entity_id, period_end, seq DESC);
        CREATE VIEW v_csrd_reporting_role_live AS
            SELECT DISTINCT ON (org_id, reporting_entity_id, period_end) *
            FROM csrd_reporting_role ORDER BY org_id, reporting_entity_id, period_end, seq DESC;
        CREATE FUNCTION prevent_csrd_role_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'csrd_reporting_role is append-only: state the role again';
        END $$;
        CREATE TRIGGER trg_csrd_role_worm BEFORE UPDATE OR DELETE ON csrd_reporting_role
            FOR EACH ROW EXECUTE FUNCTION prevent_csrd_role_mutation();

        ALTER TABLE site_period_values DROP CONSTRAINT ck_site_period_measure;
        ALTER TABLE site_period_values ADD CONSTRAINT ck_site_period_measure
            CHECK (measure IN ('carrying_amount', 'net_revenue', 'carrying_amount_adapted'));
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM csrd_reporting_role)
               OR EXISTS (SELECT 1 FROM site_period_values WHERE measure = 'carrying_amount_adapted') THEN
                RAISE EXCEPTION 'cannot downgrade csrd_role_20260930: reporting roles or adapted carrying amounts are recorded';
            END IF;
        END $$;
    """)
    op.execute("""
        ALTER TABLE site_period_values DROP CONSTRAINT ck_site_period_measure;
        ALTER TABLE site_period_values ADD CONSTRAINT ck_site_period_measure
            CHECK (measure IN ('carrying_amount', 'net_revenue'));
        DROP VIEW v_csrd_reporting_role_live;
        DROP TABLE csrd_reporting_role;
        DROP FUNCTION prevent_csrd_role_mutation();
    """)
