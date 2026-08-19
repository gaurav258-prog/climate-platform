"""drought_feature_store

Completes the drought hazard substrate (Tier 2). `drought` was declared in the
canonical vocabulary but, unlike flood/heat/wildfire, had no feature store — so
no model could be trained to write drought canonical_scores. This adds
ml_features_drought, mirroring the existing feature stores (TimescaleDB
hypertable when available, plain table otherwise).

The drought MODEL that fills these features and writes canonical scores is
separate ML work, not part of this migration. This is the schema substrate that
makes drought a first-class hazard, ready for that model and for the agriculture
sector that consumes drought scores.

Revision ID: e1f4a5b6c7d8
Revises: c8d2b3e4f5a6
Create Date: 2026-06-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f4a5b6c7d8"
down_revision: Union[str, None] = "c8d2b3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_timescale() -> bool:
    """Probe for TimescaleDB. Uses a savepoint so a failed CREATE EXTENSION on
    plain Postgres rolls back cleanly instead of poisoning the transaction."""
    conn = op.get_bind()
    conn.execute(sa.text("SAVEPOINT _ts_probe"))
    try:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        conn.execute(sa.text("RELEASE SAVEPOINT _ts_probe"))
        return True
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT _ts_probe"))
        conn.execute(sa.text("RELEASE SAVEPOINT _ts_probe"))
        return False


def upgrade() -> None:
    op.create_table(
        "ml_features_drought",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spi_3month", sa.Numeric()),
        sa.Column("spei_3month", sa.Numeric()),
        sa.Column("soil_moisture_percentile", sa.Numeric()),
        sa.Column("precipitation_deficit_mm", sa.Numeric()),
        sa.Column("evapotranspiration_mm", sa.Numeric()),
        sa.Column("ndvi_index", sa.Numeric()),
        sa.Column("ndvi_anomaly_vs_baseline", sa.Numeric()),
        sa.Column("era5_temp_anomaly_c", sa.Numeric()),
        sa.Column("days_since_significant_rain", sa.Integer()),
        sa.Column("reservoir_storage_pct", sa.Numeric()),
        sa.Column("drought_occurred", sa.Boolean()),
        sa.Column("label_source", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("feature_id", "observed_at"),
    )
    if _has_timescale():
        op.execute(
            "SELECT create_hypertable('ml_features_drought', 'observed_at', "
            "chunk_time_interval => INTERVAL '3 months')"
        )
    op.execute(
        "CREATE INDEX idx_drought_features_cell "
        "ON ml_features_drought (h3_cell, observed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_drought_features_cell")
    op.drop_table("ml_features_drought")
