"""bank_disclosure_submissions

Banking's live disclosure flow ("Publish disclosure" in Reports.jsx -> a generic
approval_requests row) has no reporting-period concept and no "view prior
submissions" capability -- a real gap given banks report on a fixed regulatory
cadence. A parallel legacy system (regulatory_packages / ml/regulatory/packager.py
/ api/routers/packages.py) already modelled period tracking + maker/checker +
immutable snapshots well, but is dead code: it authenticates via the old
cp_live_ API-key scheme (incompatible with the JWT session the live UI holds),
its ECB/CSRD builders query the wrong legacy customer_locations table instead
of bank_assets, and its docstring *claims* DB-trigger-enforced immutability
that was never actually created in that migration.

This adds a fresh, JWT-native table with genuine DB-level immutability (a full
BEFORE UPDATE/DELETE state-machine trigger, not a docstring claim), real
period_start/period_end tracking, and a snapshot that freezes BOTH the rollup
and the full per-asset detail -- a rollup-only snapshot can't later prove which
specific assets produced a value-at-risk number once bank_assets/
bank_asset_valuations have since been edited or re-scored.

Release/rejection is gated through the EXISTING approval_requests maker/checker
inbox (api/routers/approvals.py) rather than a second parallel checker UI --
approval_requests already has org-scoped audit, a working Admin UI, and a DB
CHECK enforcing checker <> maker. A new submissions.release permission is
seeded (and granted to the existing 'approver' role) because that role already
holds both reports.publish and approvals.decide; without a narrower permission
any other approver-role user could release a regulatory submission as casually
as an ordinary approval.

Revision ID: e2f3a4b5c6d7
Revises: d0e1f2a3b4c5
Create Date: 2026-07-05

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DDL = """
CREATE TABLE IF NOT EXISTS bank_disclosure_submissions (
    submission_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
    framework           VARCHAR(30) NOT NULL DEFAULT 'TCFD_EU_TAXONOMY',
    period_label        VARCHAR(50) NOT NULL,
    period_start        DATE NOT NULL,
    period_end          DATE NOT NULL,
    scenario            VARCHAR(30) NOT NULL,
    horizon             VARCHAR(20) NOT NULL,
    snapshot            JSONB NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'released', 'rejected')),
    maker_user_id       UUID NOT NULL REFERENCES users(user_id),
    maker_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    checker_user_id     UUID REFERENCES users(user_id),
    checker_at          TIMESTAMPTZ,
    released_at         TIMESTAMPTZ,
    approval_request_id UUID REFERENCES approval_requests(request_id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (checker_user_id IS NULL OR checker_user_id <> maker_user_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bank_submissions_draft_period
    ON bank_disclosure_submissions (org_id, framework, period_start, period_end)
    WHERE status = 'draft';

CREATE INDEX IF NOT EXISTS ix_bank_submissions_org_period
    ON bank_disclosure_submissions (org_id, period_start DESC);
"""

TRIGGER_FN = """
CREATE OR REPLACE FUNCTION prevent_submission_mutation() RETURNS TRIGGER AS $$
DECLARE chk bank_disclosure_submissions;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'bank_disclosure_submissions: DELETE is not permitted; reject instead';
    END IF;

    IF NEW IS NOT DISTINCT FROM OLD THEN
        RETURN NEW;
    END IF;

    IF OLD.status IN ('released', 'rejected') THEN
        RAISE EXCEPTION 'bank_disclosure_submissions: % submissions are immutable', OLD.status;
    END IF;

    -- OLD.status = 'draft' from here on.
    IF NEW.status = 'draft' THEN
        chk := NEW;
        chk.snapshot := OLD.snapshot;
        chk.scenario := OLD.scenario;
        chk.horizon := OLD.horizon;
        chk.approval_request_id := OLD.approval_request_id;
        IF chk IS DISTINCT FROM OLD THEN
            RAISE EXCEPTION 'bank_disclosure_submissions: only snapshot/scenario/horizon/approval_request_id may change while draft';
        END IF;
    ELSIF NEW.status = 'released' THEN
        IF NEW.checker_user_id IS NULL OR NEW.checker_user_id = NEW.maker_user_id THEN
            RAISE EXCEPTION 'bank_disclosure_submissions: release requires a checker distinct from the maker';
        END IF;
        IF NEW.released_at IS NULL THEN
            RAISE EXCEPTION 'bank_disclosure_submissions: released_at must be set on release';
        END IF;
    ELSIF NEW.status = 'rejected' THEN
        IF NEW.checker_user_id IS NULL THEN
            RAISE EXCEPTION 'bank_disclosure_submissions: rejection requires a checker';
        END IF;
    ELSE
        RAISE EXCEPTION 'bank_disclosure_submissions: invalid status transition % -> %', OLD.status, NEW.status;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS prevent_update_bank_submissions ON bank_disclosure_submissions;
CREATE TRIGGER prevent_update_bank_submissions
    BEFORE UPDATE ON bank_disclosure_submissions
    FOR EACH ROW EXECUTE FUNCTION prevent_submission_mutation();

DROP TRIGGER IF EXISTS prevent_delete_bank_submissions ON bank_disclosure_submissions;
CREATE TRIGGER prevent_delete_bank_submissions
    BEFORE DELETE ON bank_disclosure_submissions
    FOR EACH ROW EXECUTE FUNCTION prevent_submission_mutation();
"""

PERMISSION_SEED = """
INSERT INTO permissions (code, description)
VALUES ('submissions.release', 'Release a regulatory disclosure submission (checker)')
ON CONFLICT (code) DO NOTHING;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.role_id, p.permission_id
FROM roles r
CROSS JOIN permissions p
WHERE r.name = 'approver' AND p.code = 'submissions.release'
ON CONFLICT DO NOTHING;
"""


def upgrade() -> None:
    op.execute(DDL)
    op.execute(TRIGGER_FN)
    op.execute(PERMISSION_SEED)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS prevent_delete_bank_submissions ON bank_disclosure_submissions")
    op.execute("DROP TRIGGER IF EXISTS prevent_update_bank_submissions ON bank_disclosure_submissions")
    op.execute("DROP FUNCTION IF EXISTS prevent_submission_mutation()")
    op.execute("DROP TABLE IF EXISTS bank_disclosure_submissions")
    op.execute("DELETE FROM role_permissions WHERE permission_id IN (SELECT permission_id FROM permissions WHERE code = 'submissions.release')")
    op.execute("DELETE FROM permissions WHERE code = 'submissions.release'")
