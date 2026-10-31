"""An insurance undertaking at the head of a group owes its own ORSA beside the group's (E353): "every insurance undertaking
and reinsurance undertaking shall conduct its own risk and solvency assessment" (Directive 2009/138/EC Art. 45(1)), and the
participating undertaking the group's "at the level of the group" (Art. 246(4)) — two reports of one entity, told apart by
their role as nat-cat's are (E348), each with its own answers; and the ORSA is owed every year with no calendar date of its
own: its report is due "within 2 weeks after concluding the assessment" (Delegated Regulation (EU) 2015/35 Art. 312(1)(b)),
a day the undertaking chooses.

  template_answers       + filing_role ('solo' | 'consolidated', an entity's only): which of an entity's two reports an
                         answer is for; ux_template_answers gains it. Existing ORSA answers keep the reading they were
                         given under (an entity with entities below it answered for its group, E350)
  regulatory_obligation  due_date may be NULL — for the ORSA only (ck_obligation_due_or_conclusion): its filing's
                         conclusion gives the date
  provided_datapoint     an ORSA value of an entity is stated for one of its reports (as Solvency II nat-cat's, E348):
                         existing ones keep the reading they were stated under

Downgrade refuses while an obligation has no date, or an entity holds ORSA answers for its own report or for both: the
earlier shape reads every answer of an entity with entities below it as its group's.

Revision ID: orsa_parent_own_20261031
Revises: filing_scope_role_20261029
"""
from typing import Sequence, Union

from alembic import op

revision: str = "orsa_parent_own_20261031"
down_revision: Union[str, None] = "filing_scope_role_20261029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-000000000351"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'insurer', 'ES');
                 INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, filing_role)
                 VALUES ('{_ORG}', 'insurer_orsa_climate', '2026-12-31', 'FY2026', NULL, 'annual', 'whole_org');""",
    "cleanup": f"""DELETE FROM regulatory_obligation WHERE org_id = '{_ORG}'; DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}

_HAS_CHILDREN = "EXISTS (SELECT 1 FROM reporting_entities c WHERE c.parent_entity_id = {col})"


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE template_answers ADD COLUMN filing_role TEXT;
        ALTER TABLE template_answers ADD CONSTRAINT ck_template_answers_role
            CHECK (filing_role IS NULL OR (filing_role IN ('solo', 'consolidated') AND reporting_entity_id IS NOT NULL));
        UPDATE template_answers a SET filing_role =
               CASE WHEN {_HAS_CHILDREN.format(col='a.reporting_entity_id')} THEN 'consolidated' ELSE 'solo' END
         WHERE a.family = 'sii_climate' AND a.reporting_entity_id IS NOT NULL;
        ALTER TABLE template_answers DROP CONSTRAINT ux_template_answers;
        ALTER TABLE template_answers ADD CONSTRAINT ux_template_answers
            UNIQUE NULLS NOT DISTINCT (org_id, fund_id, reporting_entity_id, filing_role, family, document, period_end, item_id);

        ALTER TABLE regulatory_obligation ALTER COLUMN due_date DROP NOT NULL;
        ALTER TABLE regulatory_obligation ADD CONSTRAINT ck_obligation_due_or_conclusion
            CHECK (due_date IS NOT NULL OR framework = 'insurer_orsa_climate');

        UPDATE provided_datapoint p SET filing_role =
               CASE WHEN {_HAS_CHILDREN.format(col='p.reporting_entity_id')} THEN 'consolidated' ELSE 'solo' END
         WHERE p.framework = 'insurer_orsa_climate' AND p.reporting_entity_id IS NOT NULL AND p.filing_role IS NULL;
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_obligation WHERE due_date IS NULL)
               OR EXISTS (SELECT 1 FROM template_answers a WHERE a.filing_role = 'solo'
                          AND {_HAS_CHILDREN.format(col='a.reporting_entity_id')})
               OR EXISTS (SELECT 1 FROM template_answers GROUP BY org_id, fund_id, reporting_entity_id, family, document,
                          period_end, item_id HAVING count(*) > 1)
               OR EXISTS (SELECT 1 FROM provided_datapoint p WHERE p.framework = 'insurer_orsa_climate'
                          AND p.status IN ('pending', 'attested') AND p.filing_role = 'solo'
                          AND {_HAS_CHILDREN.format(col='p.reporting_entity_id')}) THEN
                RAISE EXCEPTION 'cannot downgrade orsa_parent_own_20261031: an ORSA is owed with no date, or an entity holds '
                                'its own ORSA beside its group''s';
            END IF;
        END $$;
        UPDATE provided_datapoint SET filing_role = NULL WHERE framework = 'insurer_orsa_climate';
        ALTER TABLE regulatory_obligation DROP CONSTRAINT ck_obligation_due_or_conclusion;
        ALTER TABLE regulatory_obligation ALTER COLUMN due_date SET NOT NULL;
        ALTER TABLE template_answers DROP CONSTRAINT ux_template_answers;
        ALTER TABLE template_answers ADD CONSTRAINT ux_template_answers
            UNIQUE NULLS NOT DISTINCT (org_id, fund_id, reporting_entity_id, family, document, period_end, item_id);
        ALTER TABLE template_answers DROP CONSTRAINT ck_template_answers_role;
        ALTER TABLE template_answers DROP COLUMN filing_role;
    """)
