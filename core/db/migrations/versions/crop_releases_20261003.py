"""FAOSTAT crop production arrives as a reviewed release, never straight into the store (E148).

FAOSTAT publishes its production file about once a year and revises earlier years in it. The crop calibrations, the
realised-exposure and seasonal-arrears views and the world-crop context all read crop_yield_observations, so a new
file must not change them unseen. A scheduled fetch STAGES the file as a release with its difference against what is
held; one platform operator proposes landing it, a second approves (four eyes); only then are the rows written, the
replaced values kept in the release.

  crop_yield_releases       one per publisher file (sha-256): where and when it was fetched, its difference
                            (summary), status staged → proposed → landed, or rejected; the approval request
  crop_yield_release_rows   the rows that differ (append-only): added; revised — the publisher's production or area
                            changed; recomputed — only the derived yield / year-on-year changed (our stated rounding
                            rule) — each revised or recomputed row with the value held before
  permission reference.release_review   propose and decide a reference release (granted to platform-operator, with
                                        approvals.view / create / decide in its own organisation)

Downgrade refuses while a release is recorded (its history would be lost).

Revision ID: crop_releases_20261003
Revises: p3_t1_revenue_20261002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "crop_releases_20261003"
down_revision: Union[str, None] = "p3_t1_revenue_20261002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# A recorded release: the downgrade has no table to keep it, so it must refuse
# (scripts/check_migration_roundtrip.py plants this and requires the refusal).
REFUSAL_PROBE = {
    "setup": """INSERT INTO crop_yield_releases (source, file_sha256, file_bytes, origin_url, summary)
                VALUES ('refusal probe', repeat('0', 64), 1, 'https://example.invalid/probe', '{}');""",
    "cleanup": """DELETE FROM crop_yield_releases WHERE source = 'refusal probe';""",
}

_GRANTS = ("approvals.view", "approvals.create", "approvals.decide", "reference.release_review")


def upgrade() -> None:
    op.execute("""
        CREATE TABLE crop_yield_releases (
            release_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            seq                 bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
            source              varchar(200) NOT NULL,
            file_sha256         char(64) NOT NULL,
            file_bytes          bigint NOT NULL CHECK (file_bytes > 0),
            origin_url          text NOT NULL,
            last_modified       text,
            etag                text,
            fetched_at          timestamptz NOT NULL DEFAULT now(),
            summary             jsonb NOT NULL,
            status              varchar(12) NOT NULL DEFAULT 'staged'
                                CHECK (status IN ('staged', 'proposed', 'landed', 'rejected')),
            approval_request_id uuid REFERENCES approval_requests(request_id),
            decided_by          uuid REFERENCES users(user_id),
            decided_at          timestamptz,
            decision_reason     text,
            landed_at           timestamptz,
            CHECK ((status = 'landed') = (landed_at IS NOT NULL)),
            CHECK (status IN ('staged', 'proposed') OR decided_at IS NOT NULL)
        );
        CREATE UNIQUE INDEX ux_crop_release_file ON crop_yield_releases (source, file_sha256);
        CREATE UNIQUE INDEX ux_crop_release_open ON crop_yield_releases (source) WHERE status IN ('staged', 'proposed');

        CREATE TABLE crop_yield_release_rows (
            release_id        uuid NOT NULL REFERENCES crop_yield_releases(release_id),
            commodity         varchar(80) NOT NULL,
            country           varchar(3) NOT NULL,
            season_year       integer NOT NULL,
            change            varchar(10) NOT NULL CHECK (change IN ('added', 'revised', 'recomputed')),
            production_tonnes numeric(16,1),
            area_harvested_ha numeric(16,1),
            yield_tonnes_ha   numeric(12,4),
            yoy_change_pct    numeric(8,2),
            note              text,
            held_before       jsonb,
            PRIMARY KEY (release_id, commodity, country, season_year),
            CHECK ((change = 'added') = (held_before IS NULL))
        );

        CREATE FUNCTION prevent_crop_release_row_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'crop_yield_release_rows is append-only: a release is the publisher''s file as received';
        END $$;
        CREATE TRIGGER trg_crop_release_rows_append_only BEFORE UPDATE OR DELETE ON crop_yield_release_rows
            FOR EACH ROW EXECUTE FUNCTION prevent_crop_release_row_mutation();

        INSERT INTO permissions (code, description)
        VALUES ('reference.release_review', 'Tellumen platform operator — review, propose and approve a reference '
                                            'data release (e.g. FAOSTAT crop production) before it lands')
        ON CONFLICT (code) DO NOTHING;
    """)
    op.execute(f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.role_id, p.permission_id FROM roles r JOIN organizations o ON o.org_id = r.org_id
        JOIN permissions p ON p.code IN ({", ".join(f"'{c}'" for c in _GRANTS)})
        WHERE o.type = 'platform' AND r.name = 'platform-operator'
        ON CONFLICT DO NOTHING;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM crop_yield_releases) THEN
            RAISE EXCEPTION 'crop_releases_20261003 downgrade: reference releases are recorded — no table before this '
                            'revision keeps them';
          END IF;
        END $$;
        DROP TABLE crop_yield_release_rows;
        DROP FUNCTION prevent_crop_release_row_mutation();
        DROP TABLE crop_yield_releases;
    """)
    # the approvals grants existed for customer roles before; only the platform-operator grants made here go
    op.execute("""
        DELETE FROM role_permissions rp USING roles r, organizations o, permissions p
        WHERE rp.role_id = r.role_id AND o.org_id = r.org_id AND p.permission_id = rp.permission_id
          AND o.type = 'platform' AND r.name = 'platform-operator'
          AND p.code IN ('approvals.view', 'approvals.create', 'approvals.decide', 'reference.release_review');
        DELETE FROM permissions WHERE code = 'reference.release_review';
    """)
