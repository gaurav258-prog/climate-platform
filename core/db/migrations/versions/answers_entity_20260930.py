"""A template answer can belong to one reporting entity.

An ORSA (Directive 2009/138/EC Art. 45, 45a) is the undertaking's own assessment — each insurance undertaking has one,
and the group has its own (Art. 246); a pre-emptive recovery plan is drawn up per undertaking or for the group
(Directive (EU) 2025/1 Arts 5, 7). template_answers.reporting_entity_id names the entity an answer belongs to; NULL =
the organisation as a whole (every answer held before this migration, unchanged in meaning). A fund's answer has no
entity.

Revision ID: answers_entity_20260930
Revises: filing_disclosure_date_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "answers_entity_20260930"
down_revision: Union[str, None] = "filing_disclosure_date_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee7', 'refusal probe', 'insurer', 'DE');
                INSERT INTO reporting_entities (entity_id, org_id, name, kind) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee8', '0bbe0bbe-0000-4000-8000-00000000fee7', 'probe', 'legal_entity');
                INSERT INTO template_answers (org_id, family, document, item_id, value, reporting_entity_id)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee7', 'sii_climate', 'orsa_climate', 'sfcr.actions', '{"text": "x"}', '0bbe0bbe-0000-4000-8000-00000000fee8');""",
    "cleanup": """DELETE FROM template_answers WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee7';
                  DELETE FROM reporting_entities WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee7';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee7';""",
}


def upgrade() -> None:
    op.execute("""ALTER TABLE template_answers ADD COLUMN reporting_entity_id UUID
                  REFERENCES reporting_entities(entity_id) ON DELETE RESTRICT,
                  ADD CONSTRAINT ck_template_answers_one_subject CHECK (fund_id IS NULL OR reporting_entity_id IS NULL)""")
    op.execute("ALTER TABLE template_answers DROP CONSTRAINT ux_template_answers")
    op.execute("""ALTER TABLE template_answers ADD CONSTRAINT ux_template_answers
                  UNIQUE NULLS NOT DISTINCT (org_id, fund_id, reporting_entity_id, family, document, period_end, item_id)""")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM template_answers WHERE reporting_entity_id IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade answers_entity_20260930: answers belong to a reporting entity, which the '
                                'previous schema cannot tell from the organisation''s own';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE template_answers DROP CONSTRAINT ux_template_answers")
    op.execute("""ALTER TABLE template_answers ADD CONSTRAINT ux_template_answers
                  UNIQUE NULLS NOT DISTINCT (org_id, fund_id, family, document, period_end, item_id)""")
    op.execute("ALTER TABLE template_answers DROP CONSTRAINT ck_template_answers_one_subject, DROP COLUMN reporting_entity_id")
