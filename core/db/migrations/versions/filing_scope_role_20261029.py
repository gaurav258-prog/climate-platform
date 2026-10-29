"""A report's scope is its entity AND its role (E348): an insurance undertaking at the head of a group reports its own
S.27.01.01 for itself (ITS (EU) 2023/894 Art. 19(1)(s)(i)) as well as the group's S.27.01.04 (Art. 34(1)(s)) — two
obligations, two live filings and two sets of stated figures for one entity, told apart by the role ('solo' = its own
book, 'consolidated' = the group's).

  regulatory_obligation  ux_reg_obligation_key gains the role
  regulatory_filing      ux_reg_filing_live gains the role
  provided_datapoint     + filing_role ('solo' | 'consolidated'): the report a Solvency II value is stated for — an
                         entity's own or its group's; ux_provided_live gains it. Existing values keep the reading they
                         were stated under (services.governance.entities.filing_role_for: an entity with entities
                         below it was its group)

Downgrade refuses while an entity holds both roles (an obligation, a live filing or a stated value of each) or a value
is stated for the own book of an entity with entities below it: the earlier shape reads such a value as the group's.

Revision ID: filing_scope_role_20261029
Revises: pcaf_mortgages_20261025
"""
from typing import Sequence, Union

from alembic import op

revision: str = "filing_scope_role_20261029"
down_revision: Union[str, None] = "pcaf_mortgages_20261025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG, _ENT = "0bbe0bbe-0000-4000-8000-000000000348", "0bbe0bbe-0000-4000-8000-0000000003e1"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'insurer', 'ES');
                 INSERT INTO reporting_entities (entity_id, org_id, name, kind) VALUES ('{_ENT}', '{_ORG}', 'probe', 'legal_entity');
                 INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, entity_id, filing_role)
                 VALUES ('{_ORG}', 'insurer_solvency', '2026-12-31', 'FY2026', '2027-04-08', 'annual', '{_ENT}', 'solo'),
                        ('{_ORG}', 'insurer_solvency', '2026-12-31', 'FY2026', '2027-05-20', 'annual', '{_ENT}', 'consolidated');""",
    "cleanup": f"""DELETE FROM regulatory_obligation WHERE org_id = '{_ORG}'; DELETE FROM reporting_entities WHERE org_id = '{_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    op.execute(f"""
        DROP INDEX ux_reg_obligation_key;
        CREATE UNIQUE INDEX ux_reg_obligation_key ON regulatory_obligation (org_id, framework, period_end,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}), COALESCE(filing_role, ''));
        DROP INDEX ux_reg_filing_live;
        CREATE UNIQUE INDEX ux_reg_filing_live ON regulatory_filing (org_id, framework, period_end,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}), COALESCE(eudr_movement_id, {_NIL}), COALESCE(filing_role, ''))
            WHERE status <> ALL (ARRAY['superseded', 'withdrawn']);

        ALTER TABLE provided_datapoint ADD COLUMN filing_role TEXT;
        ALTER TABLE provided_datapoint ADD CONSTRAINT ck_provided_filing_role
            CHECK (filing_role IS NULL OR (filing_role IN ('solo', 'consolidated') AND reporting_entity_id IS NOT NULL));
        UPDATE provided_datapoint p SET filing_role =
               CASE WHEN EXISTS (SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = p.reporting_entity_id)
                    THEN 'consolidated' ELSE 'solo' END
         WHERE p.framework = 'insurer_solvency' AND p.reporting_entity_id IS NOT NULL;
        DROP INDEX ux_provided_live;
        CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint (org_id, framework, datapoint_key,
            COALESCE(reporting_period_end, '0001-01-01'::date), COALESCE(reporting_entity_id, {_NIL}),
            COALESCE(breakdown_member, ''), COALESCE(filing_role, ''))
            WHERE status = ANY (ARRAY['pending', 'attested']);
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_obligation
                       GROUP BY org_id, framework, period_end, entity_id, fund_id HAVING count(*) > 1)
               OR EXISTS (SELECT 1 FROM regulatory_filing WHERE status <> ALL (ARRAY['superseded', 'withdrawn'])
                          GROUP BY org_id, framework, period_end, entity_id, fund_id, eudr_movement_id HAVING count(*) > 1)
               OR EXISTS (SELECT 1 FROM provided_datapoint WHERE status IN ('pending', 'attested')
                          GROUP BY org_id, framework, datapoint_key, reporting_period_end, reporting_entity_id, breakdown_member
                          HAVING count(*) > 1)
               OR EXISTS (SELECT 1 FROM provided_datapoint p WHERE p.filing_role = 'solo'
                          AND EXISTS (SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = p.reporting_entity_id)) THEN
                RAISE EXCEPTION 'cannot downgrade filing_scope_role_20261029: an entity holds its own report beside its group''s';
            END IF;
        END $$;
        DROP INDEX ux_provided_live;
        CREATE UNIQUE INDEX ux_provided_live ON provided_datapoint (org_id, framework, datapoint_key,
            COALESCE(reporting_period_end, '0001-01-01'::date), COALESCE(reporting_entity_id, {_NIL}),
            COALESCE(breakdown_member, ''))
            WHERE status = ANY (ARRAY['pending', 'attested']);
        ALTER TABLE provided_datapoint DROP CONSTRAINT ck_provided_filing_role;
        ALTER TABLE provided_datapoint DROP COLUMN filing_role;
        DROP INDEX ux_reg_filing_live;
        CREATE UNIQUE INDEX ux_reg_filing_live ON regulatory_filing (org_id, framework, period_end,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}), COALESCE(eudr_movement_id, {_NIL}))
            WHERE status <> ALL (ARRAY['superseded', 'withdrawn']);
        DROP INDEX ux_reg_obligation_key;
        CREATE UNIQUE INDEX ux_reg_obligation_key ON regulatory_obligation (org_id, framework, period_end,
            COALESCE(entity_id, {_NIL}), COALESCE(fund_id, {_NIL}));
    """)
