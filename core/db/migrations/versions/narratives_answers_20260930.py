"""The last two narrative stores join the one store of template answers (template_answers).

organizations.p3esg_narratives (Pillar 3 ESG qualitative Tables 1-3, keyed 'table<n>.<row letter>') becomes the
organisation's answers to family 'bank_p3esg', document 'qualitative'; organizations.sfdr_narratives (the entity's
SFDR PAI statement sections policies / actions / engagement / standards) becomes its answers to family 'sfdr_pai',
document 'pai_statement'. Each authored text is stored as a field answer {"text": ...}; an empty text was never an
answer (both readers treat it as not authored) and is not copied. An entry the store cannot hold (not text, or a key
that is not an item id) refuses the upgrade rather than being dropped. Both columns are dropped.

Revision ID: narratives_answers_20260930
Revises: template_answers_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "narratives_answers_20260930"
down_revision: Union[str, None] = "template_answers_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (column, family, document)
_STORES = (("p3esg_narratives", "bank_p3esg", "qualitative"), ("sfdr_narratives", "sfdr_pai", "pai_statement"))

REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee2', 'refusal probe', 'bank', 'DE');
                INSERT INTO template_answers (org_id, family, document, item_id, value)
                VALUES ('0bbe0bbe-0000-4000-8000-00000000fee2', 'bank_p3esg', 'qualitative', 'table1.a', '{"percent": 5}');""",
    "cleanup": """DELETE FROM template_answers WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee2';
                  DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee2';""",
}


def upgrade() -> None:
    for column, family, document in _STORES:
        op.execute(f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM organizations WHERE {column} IS NOT NULL AND jsonb_typeof({column}) <> 'object')
                   OR EXISTS (SELECT 1 FROM organizations o, jsonb_each(o.{column}) e(k, v)
                              WHERE jsonb_typeof(o.{column}) = 'object'
                                AND (jsonb_typeof(v) NOT IN ('string', 'null') OR k !~ '^[a-z0-9_.]+$')) THEN
                    RAISE EXCEPTION 'cannot upgrade to narratives_answers_20260930: organizations.{column} '
                                    'holds an entry that is not authored text under an item key';
                END IF;
            END $$;
        """)
        op.execute(f"""
            INSERT INTO template_answers (org_id, family, document, item_id, value, updated_at)
            SELECT o.org_id, '{family}', '{document}', e.k, jsonb_build_object('text', btrim(e.v #>> '{{}}')), now()
            FROM organizations o, jsonb_each(o.{column}) e(k, v)
            WHERE jsonb_typeof(o.{column}) = 'object' AND jsonb_typeof(e.v) = 'string' AND btrim(e.v #>> '{{}}') <> ''""")
        op.execute(f"ALTER TABLE organizations DROP COLUMN {column}")


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM template_answers
                       WHERE (family, document) IN (('bank_p3esg', 'qualitative'), ('sfdr_pai', 'pai_statement'))
                         AND (fund_id IS NOT NULL OR period_end IS NOT NULL
                              OR jsonb_typeof(value -> 'text') IS DISTINCT FROM 'string' OR value - 'text' <> '{}'::jsonb)) THEN
                RAISE EXCEPTION 'cannot downgrade narratives_answers_20260930: a Pillar 3 ESG qualitative or '
                                'SFDR PAI statement answer is not the organisation''s own text, which the old columns cannot hold';
            END IF;
        END $$;
    """)
    for column, family, document in _STORES:
        op.execute(f"ALTER TABLE organizations ADD COLUMN {column} JSONB")
        op.execute(f"""
            UPDATE organizations o SET {column} = a.answers
            FROM (SELECT org_id, jsonb_object_agg(item_id, value ->> 'text') AS answers FROM template_answers
                  WHERE family = '{family}' AND document = '{document}' GROUP BY org_id) a
            WHERE a.org_id = o.org_id""")
        op.execute(f"DELETE FROM template_answers WHERE family = '{family}' AND document = '{document}'")
