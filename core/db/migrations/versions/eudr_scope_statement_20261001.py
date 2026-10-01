"""EUDR layer 4 (E107): where Annex I leaves a product's scope open — an 'ex' heading ('only the part of the heading
described') or a row that excepts part of what it names — only the operator can say whether its product is in it. The
movement keeps that statement (in scope or not, and why); the checks read it, never a platform guess.

Revision ID: eudr_scope_statement_20261001
Revises: eudr_assessment_20261001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "eudr_scope_statement_20261001"
down_revision: Union[str, None] = "eudr_assessment_20261001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORG = "0bbe0bbe-0000-4000-8000-00000000fef3"
REFUSAL_PROBE = {
    "setup": f"""INSERT INTO organizations (org_id, name, type, country) VALUES ('{_ORG}', 'refusal probe', 'manufacturer', 'NL');
                 INSERT INTO eudr_movement (org_id, kind, actor_role, planned_on, hs_code, description, customs_flow, net_mass_kg,
                                            scope_in, scope_basis)
                 VALUES ('{_ORG}', 'placing', 'operator', '2027-01-15', '151620', 'probe', true, 1, true, 'probe');""",
    "cleanup": f"""DELETE FROM eudr_movement WHERE org_id = '{_ORG}'; DELETE FROM organizations WHERE org_id = '{_ORG}';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE eudr_movement ADD COLUMN scope_in BOOLEAN, ADD COLUMN scope_basis TEXT,
            ADD CONSTRAINT ck_eudr_scope_basis CHECK (scope_in IS NULL OR scope_basis IS NOT NULL);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM eudr_movement WHERE scope_in IS NOT NULL) THEN
                RAISE EXCEPTION 'cannot downgrade eudr_scope_statement_20261001: operators have stated their products'' scope';
            END IF;
        END $$;
        ALTER TABLE eudr_movement DROP CONSTRAINT ck_eudr_scope_basis, DROP COLUMN scope_basis, DROP COLUMN scope_in;
    """)
