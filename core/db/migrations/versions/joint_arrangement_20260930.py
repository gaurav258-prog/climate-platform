"""A proportionally consolidated entity says which kind of joint arrangement it is.

ESRS treats the two differently: a joint venture is value chain (Delegated Regulation (EU) 2023/2772, ESRS 1 §67:
'associates or joint ventures, accounted for under the equity method or proportionally consolidated in the financial
statements'; 2026/1563, ESRS 1 §69-70), while the share of a joint operation's assets, liabilities, revenues and
expenses recognised in the financial statements is own operations (2026/1563, ESRS 1 AR 36). The consolidation method
alone cannot tell them apart; the undertaking states it.

Revision ID: joint_arrangement_20260930
Revises: aqueduct_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "joint_arrangement_20260930"
down_revision: Union[str, None] = "aqueduct_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ORG = "0bbe0bbe-0000-4000-8000-00000000feec"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_PROBE_ORG}', 'refusal probe', 'manufacturer', 'ES');
                 INSERT INTO reporting_entities (entity_id, org_id, name, consolidation_method, joint_arrangement)
                 VALUES (gen_random_uuid(), '{_PROBE_ORG}', 'probe JO', 'proportional', 'joint_operation');""",
    "cleanup": f"""DELETE FROM reporting_entities WHERE org_id = '{_PROBE_ORG}';
                   DELETE FROM organizations WHERE org_id = '{_PROBE_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE reporting_entities ADD COLUMN joint_arrangement TEXT
            CONSTRAINT ck_joint_arrangement CHECK (joint_arrangement IS NULL OR
                (joint_arrangement IN ('joint_operation', 'joint_venture') AND consolidation_method IN ('proportional', 'equity')));
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM reporting_entities WHERE joint_arrangement IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade joint_arrangement_20260930: entities state their joint arrangement';
            END IF;
        END $$;
    """)
    op.execute("ALTER TABLE reporting_entities DROP CONSTRAINT ck_joint_arrangement, DROP COLUMN joint_arrangement;")
