"""regulator_supervision — the supervision-scope table for the regulator portal (Phase 1).

A regulator/supervisor is a new organization type. supervision_scope maps a regulator org to the reporting
entities it oversees (its supervised population), optionally narrowed to specific frameworks and stamped with a
jurisdiction. This is the ONLY thing that grants a regulator cross-entity visibility — and the supervisor API
reads it to scope every query, so a regulator can never see an entity outside its declared population. The
mapping is deliberate governance data (who supervises whom), not inferred.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "regulator_supervision_20260906"
down_revision: Union[str, None] = "windstorm_vocab_20260905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_scope (
            supervision_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regulator_org_id   UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            supervised_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            jurisdiction       TEXT,
            frameworks         JSONB,      -- NULL = every framework applicable to the supervised entity's sector
            active             BOOLEAN NOT NULL DEFAULT TRUE,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (regulator_org_id, supervised_org_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_supervision_regulator ON supervision_scope (regulator_org_id) WHERE active")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervision_scope")
