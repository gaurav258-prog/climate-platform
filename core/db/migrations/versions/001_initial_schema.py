"""Initial schema — all tables, TimescaleDB hypertable, immutability rules, audit trigger

Revision ID: 001
Revises:
Create Date: 2026-06-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _try_execute(sql: str) -> bool:
    """Run SQL, return False if it errors — uses a savepoint so the transaction stays valid."""
    conn = op.get_bind()
    conn.execute(sa.text("SAVEPOINT _optional"))
    try:
        conn.execute(sa.text(sql))
        conn.execute(sa.text("RELEASE SAVEPOINT _optional"))
        return True
    except Exception:
        conn.execute(sa.text("ROLLBACK TO SAVEPOINT _optional"))
        conn.execute(sa.text("RELEASE SAVEPOINT _optional"))
        return False


def upgrade() -> None:
    # TimescaleDB extension — optional; falls back to plain Postgres if not installed
    timescale = _try_execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # ── model_registry ────────────────────────────────────────────────────────
    op.create_table(
        "model_registry",
        sa.Column("model_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_version", sa.String(50), nullable=False, unique=True),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("algorithm", sa.String(100), nullable=False),
        sa.Column("training_data_vintage", sa.Date(), nullable=False),
        sa.Column("training_cell_count", sa.Integer()),
        sa.Column("validation_auc", sa.Numeric(4, 3)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("activated_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── canonical_scores (TimescaleDB hypertable) ─────────────────────────────
    op.create_table(
        "canonical_scores",
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("h3_resolution", sa.SmallInteger(), nullable=False, server_default="8"),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("scenario", sa.String(50), nullable=False),
        sa.Column("time_horizon", sa.String(20), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("risk_bucket", sa.String(5), nullable=False),
        sa.Column("risk_nature", sa.String(20)),
        sa.Column("model_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("model_registry.model_id"), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("data_vintage", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shap_factors", postgresql.JSONB()),
        sa.Column("observation_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("score_id", "scored_at"),
        sa.CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_score_range"),
    )

    # Convert to TimescaleDB hypertable if available
    if timescale:
        op.execute(
            "SELECT create_hypertable('canonical_scores', 'scored_at', "
            "chunk_time_interval => INTERVAL '1 month')"
        )

    # Performance index: current active scores per cell + hazard
    op.execute(
        "CREATE INDEX idx_scores_cell_hazard "
        "ON canonical_scores (h3_cell, hazard_type, scenario, time_horizon) "
        "WHERE valid_to IS NULL"
    )

    # Immutability: no UPDATEs, no DELETEs on canonical_scores
    # TimescaleDB hypertables do not support RULES — use triggers instead
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_canonical_score_mutation() RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'canonical_scores is append-only: % operations are not permitted',
                TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER prevent_update_canonical_scores
        BEFORE UPDATE ON canonical_scores
        FOR EACH ROW EXECUTE FUNCTION prevent_canonical_score_mutation();
    """)
    op.execute("""
        CREATE TRIGGER prevent_delete_canonical_scores
        BEFORE DELETE ON canonical_scores
        FOR EACH ROW EXECUTE FUNCTION prevent_canonical_score_mutation();
    """)

    # ── satellite_observations ────────────────────────────────────────────────
    op.create_table(
        "satellite_observations",
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("h3_resolution", sa.SmallInteger(), nullable=False, server_default="8"),
        sa.Column("source_provider", sa.String(100), nullable=False),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("raw_value", sa.Numeric()),
        sa.Column("raw_unit", sa.String(50)),
        sa.Column("quality_flag", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("quality_notes", sa.Text()),
        sa.Column("cog_uri", sa.Text()),
        sa.Column("adapter_version", sa.String(50), nullable=False),
    )
    op.execute(
        "CREATE INDEX idx_obs_cell_hazard_time "
        "ON satellite_observations (h3_cell, hazard_type, observed_at DESC)"
    )

    # ── ml_features_flood ─────────────────────────────────────────────────────
    op.create_table(
        "ml_features_flood",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sar_backscatter_db", sa.Numeric()),
        sa.Column("backscatter_anomaly_7d", sa.Numeric()),
        sa.Column("glofas_discharge_m3s", sa.Numeric()),
        sa.Column("discharge_vs_return_2yr", sa.Numeric()),
        sa.Column("dem_elevation_m", sa.Numeric()),
        sa.Column("dem_slope_degrees", sa.Numeric()),
        sa.Column("distance_to_water_km", sa.Numeric()),
        sa.Column("soil_saturation_index", sa.Numeric()),
        sa.Column("precipitation_7d_mm", sa.Numeric()),
        sa.Column("era5_historical_flood_freq", sa.Numeric()),
        sa.Column("flood_occurred", sa.Boolean()),
        sa.Column("label_source", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("feature_id", "observed_at"),
    )
    if timescale:
        op.execute(
            "SELECT create_hypertable('ml_features_flood', 'observed_at', "
            "chunk_time_interval => INTERVAL '3 months')"
        )
    op.execute(
        "CREATE INDEX idx_flood_features_cell "
        "ON ml_features_flood (h3_cell, observed_at DESC)"
    )

    # ── ml_features_heat ──────────────────────────────────────────────────────
    op.create_table(
        "ml_features_heat",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lst_kelvin", sa.Numeric()),
        sa.Column("lst_anomaly_vs_baseline", sa.Numeric()),
        sa.Column("era5_temp_2m_c", sa.Numeric()),
        sa.Column("era5_temp_30yr_mean", sa.Numeric()),
        sa.Column("era5_temp_trend_per_decade", sa.Numeric()),
        sa.Column("urban_heat_island_factor", sa.Numeric()),
        sa.Column("population_density", sa.Numeric()),
        sa.Column("days_above_35c_ytd", sa.Integer()),
        sa.Column("heat_event_occurred", sa.Boolean()),
        sa.Column("label_source", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("feature_id", "observed_at"),
    )
    if timescale:
        op.execute(
            "SELECT create_hypertable('ml_features_heat', 'observed_at', "
            "chunk_time_interval => INTERVAL '3 months')"
        )

    # ── ml_features_wildfire ──────────────────────────────────────────────────
    op.create_table(
        "ml_features_wildfire",
        sa.Column("feature_id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("firms_frp_mw", sa.Numeric()),
        sa.Column("firms_confidence_pct", sa.Integer()),
        sa.Column("effis_fire_weather_index", sa.Numeric()),
        sa.Column("ndvi_index", sa.Numeric()),
        sa.Column("ndvi_anomaly_vs_baseline", sa.Numeric()),
        sa.Column("gfs_wind_speed_ms", sa.Numeric()),
        sa.Column("gfs_relative_humidity_pct", sa.Numeric()),
        sa.Column("days_since_last_rain", sa.Integer()),
        sa.Column("fire_occurred", sa.Boolean()),
        sa.Column("label_source", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("feature_id", "observed_at"),
    )
    if timescale:
        op.execute(
            "SELECT create_hypertable('ml_features_wildfire', 'observed_at', "
            "chunk_time_interval => INTERVAL '3 months')"
        )

    # ── customer_locations ────────────────────────────────────────────────────
    op.create_table(
        "customer_locations",
        sa.Column("location_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_name", sa.String(500)),
        sa.Column("latitude", sa.Numeric(10, 7)),
        sa.Column("longitude", sa.Numeric(10, 7)),
        sa.Column("h3_cell_r8", sa.String(20)),
        sa.Column("h3_cell_r7", sa.String(20)),
        sa.Column("asset_type", sa.String(100)),
        sa.Column("asset_value", sa.Numeric(18, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.execute(
        "CREATE INDEX idx_locations_customer "
        "ON customer_locations (customer_id) WHERE is_active = true"
    )

    # ── alert_configs ─────────────────────────────────────────────────────────
    op.create_table(
        "alert_configs",
        sa.Column("config_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("location_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("customer_locations.location_id")),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("scenario", sa.String(50), nullable=False, server_default="'baseline'"),
        sa.Column("alert_threshold", sa.Numeric(5, 2), nullable=False),
        sa.Column("notification_channels", postgresql.JSONB(), nullable=False),
        sa.Column("maker_user_id", sa.String(255)),
        sa.Column("maker_at", sa.DateTime(timezone=True)),
        sa.Column("checker_user_id", sa.String(255)),
        sa.Column("checker_at", sa.DateTime(timezone=True)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── alert_events ──────────────────────────────────────────────────────────
    op.create_table(
        "alert_events",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("config_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("alert_configs.config_id"), nullable=False),
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("canonical_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("alert_threshold", sa.Numeric(5, 2), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("notification_status", postgresql.JSONB()),
    )

    # ── parametric_contracts ──────────────────────────────────────────────────
    op.create_table(
        "parametric_contracts",
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contract_ref", sa.String(100), nullable=False, unique=True),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("coverage_h3_cells", postgresql.ARRAY(sa.String())),
        sa.Column("trigger_threshold", sa.Numeric(5, 2), nullable=False),
        sa.Column("payout_currency", sa.String(3), nullable=False),
        sa.Column("payout_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("contract_start", sa.Date(), nullable=False),
        sa.Column("contract_end", sa.Date(), nullable=False),
        sa.Column("webhook_endpoint", sa.Text(), nullable=False),
        sa.Column("maker_user_id", sa.String(255), nullable=False),
        sa.Column("maker_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checker_user_id", sa.String(255), nullable=False),
        sa.Column("checker_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── trigger_events (immutable) ────────────────────────────────────────────
    op.create_table(
        "trigger_events",
        sa.Column("trigger_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("parametric_contracts.contract_id"), nullable=False),
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("canonical_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("trigger_threshold", sa.Numeric(5, 2), nullable=False),
        sa.Column("observation_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("shap_factors", postgresql.JSONB(), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("webhook_status", sa.String(50)),
        sa.Column("webhook_response", postgresql.JSONB()),
    )

    # DB-level immutability for trigger events — legally binding records
    op.execute(
        "CREATE RULE no_update_trigger_events AS "
        "ON UPDATE TO trigger_events DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE no_delete_trigger_events AS "
        "ON DELETE TO trigger_events DO INSTEAD NOTHING"
    )

    # ── regulatory_packages ───────────────────────────────────────────────────
    op.create_table(
        "regulatory_packages",
        sa.Column("package_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("framework", sa.String(50), nullable=False),
        sa.Column("reporting_period_start", sa.Date(), nullable=False),
        sa.Column("reporting_period_end", sa.Date(), nullable=False),
        sa.Column("score_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("methodology_doc_uri", sa.Text(), nullable=False),
        sa.Column("package_data", postgresql.JSONB(), nullable=False),
        sa.Column("maker_user_id", sa.String(255), nullable=False),
        sa.Column("maker_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checker_user_id", sa.String(255)),
        sa.Column("checker_at", sa.DateTime(timezone=True)),
        sa.Column("is_released", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── outcome_feedback ──────────────────────────────────────────────────────
    op.create_table(
        "outcome_feedback",
        sa.Column("feedback_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("h3_cell", sa.String(20), nullable=False),
        sa.Column("hazard_type", sa.String(50), nullable=False),
        sa.Column("predicted_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("predicted_bucket", sa.String(5), nullable=False),
        sa.Column("event_occurred", sa.Boolean(), nullable=False),
        sa.Column("confirmed_intensity", sa.Numeric()),
        sa.Column("intensity_unit", sa.String(50)),
        sa.Column("outcome_source", sa.String(100), nullable=False),
        sa.Column("outcome_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prediction_lead_days", sa.Integer()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
    )

    # ── audit_log ─────────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("performed_by", sa.String(255), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("details", postgresql.JSONB()),
    )

    # DB-level audit trigger on canonical_scores
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_canonical_score() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO audit_log (table_name, record_id, action, performed_by, details)
            VALUES (
                'canonical_scores',
                NEW.score_id,
                'INSERT',
                COALESCE(current_setting('app.user_id', true), 'system'),
                jsonb_build_object(
                    'model_version', NEW.model_version,
                    'h3_cell',       NEW.h3_cell,
                    'hazard_type',   NEW.hazard_type,
                    'risk_score',    NEW.risk_score,
                    'risk_bucket',   NEW.risk_bucket,
                    'scenario',      NEW.scenario
                )
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER audit_scores_insert
        AFTER INSERT ON canonical_scores
        FOR EACH ROW EXECUTE FUNCTION audit_canonical_score();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_scores_insert ON canonical_scores")
    op.execute("DROP FUNCTION IF EXISTS audit_canonical_score()")
    op.drop_table("audit_log")
    op.drop_table("outcome_feedback")
    op.drop_table("regulatory_packages")
    op.execute("DROP RULE IF EXISTS no_delete_trigger_events ON trigger_events")
    op.execute("DROP RULE IF EXISTS no_update_trigger_events ON trigger_events")
    op.drop_table("trigger_events")
    op.drop_table("parametric_contracts")
    op.drop_table("alert_events")
    op.drop_table("alert_configs")
    op.drop_table("customer_locations")
    op.drop_table("ml_features_wildfire")
    op.drop_table("ml_features_heat")
    op.drop_table("ml_features_flood")
    op.drop_table("satellite_observations")
    op.execute("DROP TRIGGER IF EXISTS prevent_update_canonical_scores ON canonical_scores")
    op.execute("DROP TRIGGER IF EXISTS prevent_delete_canonical_scores ON canonical_scores")
    op.execute("DROP FUNCTION IF EXISTS prevent_canonical_score_mutation()")
    op.drop_table("canonical_scores")
    op.drop_table("model_registry")
