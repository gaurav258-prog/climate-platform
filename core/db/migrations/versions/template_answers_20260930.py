"""One store for the answers to template items, whatever the template: template_answers.

A template's items the platform cannot compute are answered by the reporting organisation — for itself (an insurer's
ORSA climate analysis, its recovery-plan indicators) or for one of its financial products (a fund's SFDR
pre-contractual and periodic documents). Each answer is keyed by the specification family, the document, the item id,
the subject (the organisation, or a fund) and — for a periodic document — the reference period. fund_sfdr_answers
(sfdr_product_20260929) becomes part of it and is dropped.

Revision ID: template_answers_20260930
Revises: sfdr_product_20260929
"""
from typing import Sequence, Union

from alembic import op

revision: str = "template_answers_20260930"
down_revision: Union[str, None] = "sfdr_product_20260929"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee1', 'refusal probe', 'insurer', 'DE');
                INSERT INTO template_answers (org_id, family, document, item_id, value)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee1', 'sii_climate', 'orsa_climate', 'materiality.conclusion', '{"text": "x"}');""",
    "cleanup": """DELETE FROM template_answers WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee1';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee1';""",
}


def upgrade() -> None:
    op.execute("""
        CREATE TABLE template_answers (
            answer_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id       UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            fund_id      UUID REFERENCES funds(fund_id) ON DELETE CASCADE,
            family       TEXT NOT NULL CHECK (family ~ '^[a-z0-9_]+$'),
            document     TEXT NOT NULL CHECK (document ~ '^[a-z0-9_]+$'),
            period_end   DATE,
            item_id      TEXT NOT NULL CHECK (item_id ~ '^[a-z0-9_.]+$'),
            value        JSONB NOT NULL,
            updated_by   UUID REFERENCES users(user_id),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_template_answers UNIQUE NULLS NOT DISTINCT (org_id, fund_id, family, document, period_end, item_id)
        )""")
    op.execute("CREATE INDEX ix_template_answers_subject ON template_answers (org_id, family, document)")
    op.execute("""
        INSERT INTO template_answers (org_id, fund_id, family, document, period_end, item_id, value, updated_by, updated_at)
        SELECT f.org_id, a.fund_id, 'sfdr_product', a.document, a.period_end, a.item_id, a.value, a.updated_by, a.updated_at
        FROM fund_sfdr_answers a JOIN funds f USING (fund_id)""")
    op.execute("DROP TABLE fund_sfdr_answers")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM template_answers WHERE family <> 'sfdr_product' OR fund_id IS NULL
                           OR document NOT IN ('precontractual', 'periodic')) THEN
                RAISE EXCEPTION 'cannot downgrade template_answers_20260930: answers exist for templates other than a '
                                'fund''s SFDR documents, which fund_sfdr_answers cannot hold';
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE TABLE fund_sfdr_answers (
            answer_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fund_id      UUID NOT NULL REFERENCES funds(fund_id) ON DELETE CASCADE,
            document     TEXT NOT NULL CHECK (document IN ('precontractual', 'periodic')),
            period_end   DATE,
            item_id      TEXT NOT NULL CHECK (item_id ~ '^[a-z0-9_.]+$'),
            value        JSONB NOT NULL,
            updated_by   UUID REFERENCES users(user_id),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_fund_sfdr_answers_period CHECK ((document = 'periodic') = (period_end IS NOT NULL)),
            CONSTRAINT ux_fund_sfdr_answers UNIQUE NULLS NOT DISTINCT (fund_id, document, period_end, item_id)
        )""")
    op.execute("""
        INSERT INTO fund_sfdr_answers (fund_id, document, period_end, item_id, value, updated_by, updated_at)
        SELECT fund_id, document, period_end, item_id, value, updated_by, updated_at FROM template_answers""")
    op.execute("DROP TABLE template_answers")
