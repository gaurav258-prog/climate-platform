"""supervision_request(+_message) — information requests, site-access requests and findings, regulator → entity.

One thread per request, visible to both sides; status flows come from supervision_profiles.json (engagement).
Also lets the entity's task board carry a task whose source is the supervisor.

Revision ID: sup_requests_20260907
Revises: sup_assign_20260907
"""
from typing import Sequence, Union

from alembic import op

revision: str = "sup_requests_20260907"
down_revision: Union[str, None] = "sup_assign_20260907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



# A row the pre-migration shape cannot hold: scripts/check_migration_roundtrip.py plants it and requires the downgrade
# to refuse, leaving the schema untouched (every refusing downgrade must carry one).
REFUSAL_PROBE = {
    "setup": """INSERT INTO organizations (org_id, name, type, country) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee1', 'refusal probe', 'bank', 'DE'); INSERT INTO regulatory_task (org_id, title, source) VALUES ('0bbe0bbe-0000-4000-8000-00000000fee1', 'refusal probe', 'supervisor');""",
    "cleanup": """DELETE FROM regulatory_task WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee1'; DELETE FROM organizations WHERE org_id = '0bbe0bbe-0000-4000-8000-00000000fee1';""",
}

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_request (
            request_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            regulator_org_id   UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            supervised_org_id  UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
            kind               TEXT NOT NULL,
            title              TEXT NOT NULL,
            body               TEXT,
            status             TEXT NOT NULL DEFAULT 'open',
            severity           TEXT,
            due_date           DATE,
            source             JSONB,                      -- where it came from (lens cell, benchmark metric, manual)
            raised_by          UUID REFERENCES users(user_id),
            raised_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at          TIMESTAMPTZ,
            closed_by          UUID REFERENCES users(user_id),
            entity_task_id     UUID                        -- the task on the entity's own board
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sup_request_reg ON supervision_request (regulator_org_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_sup_request_entity ON supervision_request (supervised_org_id, status)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS supervision_request_message (
            message_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_id   UUID NOT NULL REFERENCES supervision_request(request_id) ON DELETE CASCADE,
            side         TEXT NOT NULL,                    -- supervisor | entity
            author_id    UUID REFERENCES users(user_id),
            body         TEXT,
            status_to    TEXT,                             -- set when the message changed the status
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_sup_request_msg ON supervision_request_message (request_id, created_at)")
    # the entity's task board may now carry a task whose source is its supervisor
    op.execute("ALTER TABLE regulatory_task DROP CONSTRAINT IF EXISTS regulatory_task_source_check")
    op.execute("""ALTER TABLE regulatory_task ADD CONSTRAINT regulatory_task_source_check
                  CHECK (source IN ('manual','validation','exception','obligation','regulatory_change','decision','kri','supervisor'))""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supervision_request_message")
    op.execute("DROP TABLE IF EXISTS supervision_request")
    # the old check cannot hold supervisor-sourced tasks — refuse rather than silently delete them
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM regulatory_task WHERE source = 'supervisor') THEN
                RAISE EXCEPTION 'cannot downgrade sup_requests_20260907: % regulatory_task row(s) have source=''supervisor'', '
                                'which the prior check does not allow — resolve them first',
                                (SELECT count(*) FROM regulatory_task WHERE source = 'supervisor');
            END IF;
        END $$;
    """)
    # exactly as sup_assign_20260907 defined it
    op.execute("ALTER TABLE regulatory_task DROP CONSTRAINT IF EXISTS regulatory_task_source_check")
    op.execute("""ALTER TABLE regulatory_task ADD CONSTRAINT regulatory_task_source_check
                  CHECK (source IN ('manual','validation','exception','obligation','regulatory_change','decision','kri'))""")
