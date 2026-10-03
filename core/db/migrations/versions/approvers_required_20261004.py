"""How many PEOPLE must approve a platform change — a governed setting, not an assumption (E150).

Four eyes needs two people. With one approver in the organisation, a second person cannot exist, so the platform says
so explicitly instead of faking it: approval_policy.human_approvers is 2 (a person proposes, another approves) or 1
(the platform's system account proposes, with its evidence, and one person approves — the maker is never the checker,
so the approvals path still refuses anyone approving their own proposal). The value is the organisation's statement,
changed through the operator console and audited; the default is 2.

  approval_policy.human_approvers   smallint 1 | 2, default 2
  platform policy rows              'reference.release_land' and 'calibration.publish' for the platform organisation
                                    (human_approvers 2 until the organisation states otherwise)
  system account                    pipeline@system.tellumen.io in the platform organisation — status 'disabled', no
                                    password: it can never sign in; it is only named as the maker of an automatic
                                    proposal

Downgrade refuses while any policy states one approver (the column holds that statement).

Revision ID: approvers_required_20261004
Revises: crop_releases_20261003
"""
from typing import Sequence, Union

from alembic import op

revision: str = "approvers_required_20261004"
down_revision: Union[str, None] = "crop_releases_20261003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYSTEM_USER = "00000000-0000-4000-8000-0000000005e1"
PLATFORM_ORG = "99999999-9999-4999-8999-999999999999"

REFUSAL_PROBE = {
    "setup": """INSERT INTO approval_policy (org_id, action_key, requires_approval, human_approvers)
                VALUES (NULL, 'refusal.probe.single', true, 1);""",
    "cleanup": """DELETE FROM approval_policy WHERE action_key = 'refusal.probe.single';""",
}


def upgrade() -> None:
    op.execute("""
        ALTER TABLE approval_policy ADD COLUMN human_approvers smallint NOT NULL DEFAULT 2
            CHECK (human_approvers IN (1, 2));
    """)
    # the platform organisation and its system account exist only where the platform has been seeded
    op.execute(f"""
        INSERT INTO users (user_id, org_id, email, role, full_name, hashed_password, status, created_at)
        SELECT '{SYSTEM_USER}', '{PLATFORM_ORG}', 'pipeline@system.tellumen.io', 'system',
               'Tellumen pipeline (system account — cannot sign in)', NULL, 'disabled', now()
        WHERE EXISTS (SELECT 1 FROM organizations WHERE org_id = '{PLATFORM_ORG}')
        ON CONFLICT DO NOTHING;
        INSERT INTO approval_policy (org_id, action_key, requires_approval, human_approvers)
        SELECT '{PLATFORM_ORG}', k, true, 2 FROM unnest(ARRAY['reference.release_land', 'calibration.publish']) k
        WHERE EXISTS (SELECT 1 FROM organizations WHERE org_id = '{PLATFORM_ORG}')
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM approval_policy WHERE human_approvers = 1) THEN
            RAISE EXCEPTION 'approvers_required_20261004 downgrade: a policy states one human approver — no column '
                            'before this revision keeps that statement';
          END IF;
        END $$;
        DELETE FROM approval_policy WHERE org_id = '{PLATFORM_ORG}'
          AND action_key IN ('reference.release_land', 'calibration.publish');
        DELETE FROM users WHERE user_id = '{SYSTEM_USER}'
          AND NOT EXISTS (SELECT 1 FROM approval_requests WHERE maker_user_id = '{SYSTEM_USER}');
        ALTER TABLE approval_policy DROP COLUMN human_approvers;
    """)
