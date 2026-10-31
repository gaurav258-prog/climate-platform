"""A reporting period is its end AND its kind (E354): a financial year, or the first half of one — Pillar 3 ESG's
semi-annual disclosure (CRR Art. 433a(1)(b)(xv); services.governance.periods).

  regulatory_filing,     + period_kind ('financial_year' | 'half_year', default the year every row was); the label CHECK
  regulatory_obligation    derives the label from end and kind (periods.LABEL_SQL: FY2026 / FY2026-H1); a half-year is
                           for Pillar 3 ESG only (the one report an act owes for it) and an obligation for it is
                           semi-annual; the unique keys (live filing, obligation) gain the kind
  org_reporting_settings + reporting_period_kind (NULL = a financial year): the period the organisation prepares

The size-class statement large_institution gains 'gsii' and now reads 'large' as a large institution other than a
G-SII (services.governance.crr_filers): the upgrade refuses while a 'large' statement made before it exists, so none is
read under the new choice set without being restated.

Downgrade refuses while a half-year filing, obligation or setting exists: the earlier shape has no half-year.

Revision ID: p3_semiannual_20261031
Revises: orsa_parent_own_20261031
"""
from typing import Sequence, Union

from alembic import op

revision: str = "p3_semiannual_20261031"
down_revision: Union[str, None] = "orsa_parent_own_20261031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-000000000351"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'bank', 'ES');
                 INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, period_kind, due_date,
                                                    frequency, filing_role)
                 VALUES ('{_ORG}', 'bank_p3esg', '2026-06-30', 'FY2026-H1', 'half_year', '2026-09-30', 'semiannual',
                         'whole_org');""",
    "cleanup": f"""DELETE FROM regulatory_obligation WHERE org_id = '{_ORG}'; DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"
_LABEL = ("CASE WHEN period_kind = 'half_year' "
          "THEN 'FY' || EXTRACT(YEAR FROM period_end + INTERVAL '6 months')::int || '-H1' "
          "ELSE 'FY' || EXTRACT(YEAR FROM period_end)::int END")      # services.governance.periods.LABEL_SQL
_KIND = "period_kind IN ('financial_year', 'half_year') AND (period_kind = 'financial_year' OR framework = 'bank_p3esg')"


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM provided_datapoint WHERE framework = 'bank_p3esg'
                       AND datapoint_key = 'large_institution' AND value_text = 'large') THEN
                RAISE EXCEPTION 'p3_semiannual_20261031: a size-class statement ''large'' was made before G-SII was a '
                                'choice — restate it (gsii or large) before upgrading';
            END IF;
        END $$;
    """)
    op.execute(f"""
        ALTER TABLE regulatory_filing ADD COLUMN period_kind TEXT NOT NULL DEFAULT 'financial_year';
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_period_kind CHECK ({_KIND});
        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_filing_period_label;
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_period_label CHECK (
            CASE WHEN framework IN ('eudr_dds', 'eudr_simplified') THEN period_label LIKE '% · ' || period_end::text
                 ELSE period_label = ({_LABEL}) END);

        ALTER TABLE regulatory_obligation ADD COLUMN period_kind TEXT NOT NULL DEFAULT 'financial_year';
        ALTER TABLE regulatory_obligation ADD CONSTRAINT ck_obligation_period_kind CHECK ({_KIND});
        ALTER TABLE regulatory_obligation ADD CONSTRAINT ck_obligation_half_year_semiannual
            CHECK (period_kind = 'financial_year' OR frequency = 'semiannual');
        ALTER TABLE regulatory_obligation DROP CONSTRAINT ck_obligation_period_label;
        ALTER TABLE regulatory_obligation ADD CONSTRAINT ck_obligation_period_label CHECK (period_label = ({_LABEL}));

        ALTER TABLE org_reporting_settings ADD COLUMN reporting_period_kind TEXT;
        ALTER TABLE org_reporting_settings ADD CONSTRAINT ck_settings_period_kind
            CHECK (reporting_period_kind IS NULL OR reporting_period_kind IN ('financial_year', 'half_year'));

        DROP INDEX ux_reg_obligation_key;
        CREATE UNIQUE INDEX ux_reg_obligation_key ON regulatory_obligation (org_id, framework, period_end, period_kind,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}), COALESCE(filing_role, ''));
        DROP INDEX ux_reg_filing_live;
        CREATE UNIQUE INDEX ux_reg_filing_live ON regulatory_filing (org_id, framework, period_end, period_kind,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}), COALESCE(eudr_movement_id, {_NIL}), COALESCE(filing_role, ''))
            WHERE status <> ALL (ARRAY['superseded', 'withdrawn']);
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_filing WHERE period_kind = 'half_year')
               OR EXISTS (SELECT 1 FROM regulatory_obligation WHERE period_kind = 'half_year')
               OR EXISTS (SELECT 1 FROM org_reporting_settings WHERE reporting_period_kind = 'half_year') THEN
                RAISE EXCEPTION 'cannot downgrade p3_semiannual_20261031: a half-year period is recorded';
            END IF;
        END $$;
        DROP INDEX ux_reg_filing_live;
        CREATE UNIQUE INDEX ux_reg_filing_live ON regulatory_filing (org_id, framework, period_end,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}), COALESCE(eudr_movement_id, {_NIL}), COALESCE(filing_role, ''))
            WHERE status <> ALL (ARRAY['superseded', 'withdrawn']);
        DROP INDEX ux_reg_obligation_key;
        CREATE UNIQUE INDEX ux_reg_obligation_key ON regulatory_obligation (org_id, framework, period_end,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}), COALESCE(filing_role, ''));

        ALTER TABLE org_reporting_settings DROP CONSTRAINT ck_settings_period_kind;
        ALTER TABLE org_reporting_settings DROP COLUMN reporting_period_kind;

        ALTER TABLE regulatory_obligation DROP CONSTRAINT ck_obligation_period_label;
        ALTER TABLE regulatory_obligation ADD CONSTRAINT ck_obligation_period_label
            CHECK (period_label = 'FY' || EXTRACT(YEAR FROM period_end)::int);
        ALTER TABLE regulatory_obligation DROP CONSTRAINT ck_obligation_half_year_semiannual;
        ALTER TABLE regulatory_obligation DROP CONSTRAINT ck_obligation_period_kind;
        ALTER TABLE regulatory_obligation DROP COLUMN period_kind;

        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_filing_period_label;
        ALTER TABLE regulatory_filing ADD CONSTRAINT ck_filing_period_label CHECK (
            CASE WHEN framework IN ('eudr_dds', 'eudr_simplified') THEN period_label LIKE '% · ' || period_end::text
                 ELSE period_label = ('FY'::text || (EXTRACT(year FROM period_end))::integer) END);
        ALTER TABLE regulatory_filing DROP CONSTRAINT ck_filing_period_kind;
        ALTER TABLE regulatory_filing DROP COLUMN period_kind;
    """)
