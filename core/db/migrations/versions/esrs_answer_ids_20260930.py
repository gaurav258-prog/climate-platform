"""The answers store takes the ids the ESRS print: a standard as its document ('E1') and an item as the regulation
numbers it ('E1-6.44c') — upper case and a hyphen, which the store's first families (SFDR, Solvency II) never used.

Revision ID: esrs_answer_ids_20260930
Revises: joint_arrangement_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "esrs_answer_ids_20260930"
down_revision: Union[str, None] = "joint_arrangement_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000feed"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'manufacturer', 'ES');
                 INSERT INTO template_answers (org_id, family, document, period_end, item_id, value)
                 VALUES ('{_PROBE_ORG}', 'esrs', 'E1', '2025-12-31', 'E1-6.44c', '{{"text": "probe"}}');""",
    "cleanup": f"""DELETE FROM template_answers WHERE org_id = '{_PROBE_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE template_answers
            DROP CONSTRAINT template_answers_document_check,
            DROP CONSTRAINT template_answers_item_id_check,
            ADD CONSTRAINT template_answers_document_check CHECK (document ~ '^[A-Za-z0-9_]+$'),
            ADD CONSTRAINT template_answers_item_id_check CHECK (item_id ~ '^[A-Za-z0-9_.-]+$');
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM template_answers WHERE document !~ '^[a-z0-9_]+$' OR item_id !~ '^[a-z0-9_.]+$') THEN
                RAISE EXCEPTION 'cannot downgrade esrs_answer_ids_20260930: answers are stored under ESRS ids';
            END IF;
        END $$;
    """)
    op.execute("""
        ALTER TABLE template_answers
            DROP CONSTRAINT template_answers_document_check,
            DROP CONSTRAINT template_answers_item_id_check,
            ADD CONSTRAINT template_answers_document_check CHECK (document ~ '^[a-z0-9_]+$'),
            ADD CONSTRAINT template_answers_item_id_check CHECK (item_id ~ '^[a-z0-9_.]+$');
    """)
