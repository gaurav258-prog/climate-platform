"""An organisation's own exchange rates (multi-currency phase 2; decision 4: governed client rates).

  * fx_client_rates — append-only submissions of the organisation's treasury rates: a daily closing rate
    (basis 'closing', rate_date) or an average for a stated period (basis 'period_average', period_start..rate_date).
    The latest submission for a key wins; every earlier one stays. Used before the official sources for that
    organisation, always compared with the ECB / IMF rate for the same day or period (fx_client_rate_tolerance_pct).

Revision ID: fx_client_rates_20260926
Revises: currency_settings_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fx_client_rates_20260926"
down_revision: Union[str, None] = "currency_settings_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS fx_client_rates (
            client_rate_id  BIGSERIAL PRIMARY KEY,
            org_id          UUID NOT NULL REFERENCES organizations(org_id),
            ccy             CHAR(3) NOT NULL,
            basis           TEXT NOT NULL,
            period_start    DATE,
            rate_date       DATE NOT NULL,
            units_per_eur   NUMERIC(18, 8) NOT NULL,
            source_note     TEXT,
            submitted_by    UUID REFERENCES users(user_id),
            submitted_at    TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT ck_client_rate_basis CHECK (basis IN ('closing', 'period_average')),
            CONSTRAINT ck_client_rate_period CHECK ((basis = 'period_average') = (period_start IS NOT NULL)),
            CONSTRAINT ck_client_rate_positive CHECK (units_per_eur > 0)
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_client_rates_key
                  ON fx_client_rates (org_id, ccy, basis, rate_date, submitted_at DESC)""")
    op.execute("""
        CREATE OR REPLACE FUNCTION fx_client_rates_worm() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'fx_client_rates is append-only (submit a new rate) — % is blocked', TG_OP;
        END $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_fx_client_rates_worm ON fx_client_rates")
    op.execute("CREATE TRIGGER trg_fx_client_rates_worm BEFORE UPDATE OR DELETE ON fx_client_rates "
               "FOR EACH ROW EXECUTE FUNCTION fx_client_rates_worm()")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fx_client_rates")
    op.execute("DROP FUNCTION IF EXISTS fx_client_rates_worm()")
