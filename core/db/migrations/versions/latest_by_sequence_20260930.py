"""The 'latest' of a history table is chosen by a strictly increasing number, never by a timestamp (error log E52).

now() is the same for every row a transaction writes, and a clock can step back, so a timestamp does not order two
statements made in one transaction. site_period_values was fixed with an identity sequence (E51); two readers remained:

  asset_conflicts   the live decision on a fact is the last one resolved. Rows are opened and later resolved (updated),
                    so an insert sequence would not order resolutions: resolved_seq is drawn from its own sequence by a
                    trigger when a row becomes resolved, and cannot be changed afterwards. Existing resolved rows are
                    numbered by resolved_at, created_at, conflict_id.
  fx_client_rates   already has client_rate_id (BIGSERIAL): readers order by it; the key index follows.

Revision ID: latest_by_sequence_20260930
Revises: period_book_foundation_20260930
"""
from typing import Sequence, Union

from alembic import op

revision: str = "latest_by_sequence_20260930"
down_revision: Union[str, None] = "period_book_foundation_20260930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROBE_ASSET = "0bbe0bbe-0000-4000-8000-00000000fee8"
REFUSAL_PROBE = {
    # two decisions on one fact resolved at the same instant: only resolved_seq says which is live
    "setup": f"""INSERT INTO asset_conflicts (org_id, asset_table, asset_id, field, rule, status, resolution, resolved_at)
                 VALUES (gen_random_uuid(), 'portfolio_entities', '{_PROBE_ASSET}', 'country', 'probe', 'resolved', 'tellumen', now()),
                        (gen_random_uuid(), 'portfolio_entities', '{_PROBE_ASSET}', 'country', 'probe', 'resolved', 'client', now());""",
    "cleanup": f"DELETE FROM asset_conflicts WHERE asset_id = '{_PROBE_ASSET}';",
}


def upgrade() -> None:
    op.execute("""
        CREATE SEQUENCE asset_conflicts_resolved_seq;
        ALTER TABLE asset_conflicts ADD COLUMN resolved_seq BIGINT;
        ALTER SEQUENCE asset_conflicts_resolved_seq OWNED BY asset_conflicts.resolved_seq;

        UPDATE asset_conflicts c SET resolved_seq = o.n
        FROM (SELECT conflict_id, row_number() OVER (ORDER BY resolved_at, created_at, conflict_id) AS n
              FROM asset_conflicts WHERE status = 'resolved') o
        WHERE c.conflict_id = o.conflict_id;
        SELECT setval('asset_conflicts_resolved_seq', COALESCE((SELECT max(resolved_seq) FROM asset_conflicts), 0) + 1, false);

        ALTER TABLE asset_conflicts ADD CONSTRAINT ck_asset_conflict_resolved_seq
            CHECK ((status = 'resolved') = (resolved_seq IS NOT NULL));

        CREATE FUNCTION asset_conflict_resolved_seq() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND OLD.status = 'resolved' THEN
                NEW.resolved_seq := OLD.resolved_seq;                    -- the order of a decision is fixed once made
            ELSIF NEW.status = 'resolved' THEN
                NEW.resolved_seq := nextval('asset_conflicts_resolved_seq');
            ELSE
                NEW.resolved_seq := NULL;
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_asset_conflict_resolved_seq BEFORE INSERT OR UPDATE ON asset_conflicts
            FOR EACH ROW EXECUTE FUNCTION asset_conflict_resolved_seq();

        CREATE INDEX ix_asset_conflict_decided ON asset_conflicts (asset_table, asset_id, field, resolved_seq DESC)
            WHERE status = 'resolved';

        DROP INDEX ix_client_rates_key;
        CREATE INDEX ix_client_rates_key ON fx_client_rates (org_id, ccy, basis, rate_date, client_rate_id DESC);
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM asset_conflicts WHERE status = 'resolved'
                       GROUP BY asset_table, asset_id, field, resolved_at HAVING COUNT(*) > 1) THEN
                RAISE EXCEPTION 'cannot downgrade latest_by_sequence_20260930: two decisions on one fact share a '
                                'resolution time, and only resolved_seq says which is live';
            END IF;
        END $$;
    """)
    op.execute("""
        DROP INDEX ix_client_rates_key;
        CREATE INDEX ix_client_rates_key ON fx_client_rates (org_id, ccy, basis, rate_date, submitted_at DESC);

        DROP INDEX ix_asset_conflict_decided;
        DROP TRIGGER trg_asset_conflict_resolved_seq ON asset_conflicts;
        DROP FUNCTION asset_conflict_resolved_seq();
        ALTER TABLE asset_conflicts DROP CONSTRAINT ck_asset_conflict_resolved_seq;
        ALTER TABLE asset_conflicts DROP COLUMN resolved_seq;
        DROP SEQUENCE IF EXISTS asset_conflicts_resolved_seq;
    """)
