"""FX rates are versioned: a rate a source corrects is never lost (multi-currency phase 2).

  * fx_rate_history — append-only (trigger): whenever a stored rate's value changes (or a rate is removed), the
    previous figure is kept with when it was replaced and the new figure. A frozen filing records when its rates were
    read; any history row replaced after that for a rate it used means the filing may need restating (phase 3).
  * The daily ECB/IMF refresh re-sends unchanged rates; only a real change of value is recorded.

Revision ID: fx_rate_history_20260926
Revises: money_source_assets_20260926
"""
from typing import Sequence, Union

from alembic import op

revision: str = "fx_rate_history_20260926"
down_revision: Union[str, None] = "money_source_assets_20260926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS fx_rate_history (
            history_id       BIGSERIAL PRIMARY KEY,
            ccy              VARCHAR(3) NOT NULL,
            rate_date        DATE NOT NULL,
            source           TEXT NOT NULL,
            basis            TEXT NOT NULL,
            units_per_eur    NUMERIC(18, 6),
            eur_per_unit     NUMERIC(18, 8),
            fetched_at       TIMESTAMPTZ,
            replaced_at      TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),   -- wall clock, not transaction start
            new_units_per_eur NUMERIC(18, 6),
            change           TEXT NOT NULL,
            CONSTRAINT ck_fx_history_change CHECK (change IN ('corrected', 'removed'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_fx_history_key ON fx_rate_history (ccy, rate_date, source, basis, replaced_at)")
    op.execute("""
        CREATE OR REPLACE FUNCTION fx_rates_keep_history() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                INSERT INTO fx_rate_history (ccy, rate_date, source, basis, units_per_eur, eur_per_unit, fetched_at, change)
                VALUES (OLD.ccy, OLD.rate_date, OLD.source, OLD.basis, OLD.units_per_eur, OLD.eur_per_unit, OLD.fetched_at, 'removed');
                RETURN OLD;
            END IF;
            IF NEW.eur_per_unit IS DISTINCT FROM OLD.eur_per_unit OR NEW.units_per_eur IS DISTINCT FROM OLD.units_per_eur THEN
                INSERT INTO fx_rate_history (ccy, rate_date, source, basis, units_per_eur, eur_per_unit, fetched_at,
                                             new_units_per_eur, change)
                VALUES (OLD.ccy, OLD.rate_date, OLD.source, OLD.basis, OLD.units_per_eur, OLD.eur_per_unit, OLD.fetched_at,
                        NEW.units_per_eur, 'corrected');
            END IF;
            RETURN NEW;
        END $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_fx_rates_history ON fx_rates")
    op.execute("CREATE TRIGGER trg_fx_rates_history BEFORE UPDATE OR DELETE ON fx_rates "
               "FOR EACH ROW EXECUTE FUNCTION fx_rates_keep_history()")
    op.execute("""
        CREATE OR REPLACE FUNCTION fx_rate_history_worm() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'fx_rate_history is append-only — % is blocked', TG_OP;
        END $$ LANGUAGE plpgsql
    """)
    op.execute("DROP TRIGGER IF EXISTS trg_fx_rate_history_worm ON fx_rate_history")
    op.execute("CREATE TRIGGER trg_fx_rate_history_worm BEFORE UPDATE OR DELETE ON fx_rate_history "
               "FOR EACH ROW EXECUTE FUNCTION fx_rate_history_worm()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_fx_rates_history ON fx_rates")
    op.execute("DROP FUNCTION IF EXISTS fx_rates_keep_history()")
    op.execute("DROP TABLE IF EXISTS fx_rate_history")
    op.execute("DROP FUNCTION IF EXISTS fx_rate_history_worm()")
