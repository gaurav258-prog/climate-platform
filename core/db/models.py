"""
SQLAlchemy ORM Models for Climate Intelligence Platform

Regulatory + CRCS (Continuous Regulatory Compliance Service) Complete Models
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime,
    ForeignKey, Integer, Numeric, PrimaryKeyConstraint, Index,
    SmallInteger, String, Text, UniqueConstraint, func, DECIMAL
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ModelRegistry(Base):
    __tablename__ = "model_registry"

    model_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_version = Column(String(50), nullable=False, unique=True)
    hazard_type = Column(String(50), nullable=False)
    algorithm = Column(String(100), nullable=False)
    training_data_vintage = Column(Date, nullable=False)
    training_cell_count = Column(Integer)
    validation_auc = Column(Numeric(4, 3))
    is_active = Column(Boolean, nullable=False, default=False)
    activated_at = Column(DateTime(timezone=True))
    activated_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class CanonicalScore(Base):
    """
    The Golden Source. Append-only — no UPDATEs, no DELETEs.
    Partitioned by scored_at (TimescaleDB hypertable).
    Only the Risk Scoring Engine writes to this table.
    """
    __tablename__ = "canonical_scores"
    __table_args__ = (
        PrimaryKeyConstraint("score_id", "scored_at"),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_risk_score_range"),
    )

    score_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    h3_cell = Column(String(20), nullable=False)
    h3_resolution = Column(SmallInteger, nullable=False, default=8)
    hazard_type = Column(String(50), nullable=False)
    scenario = Column(String(50), nullable=False)
    time_horizon = Column(String(20), nullable=False)
    risk_score = Column(Numeric(5, 2), nullable=False)
    risk_bucket = Column(String(5), nullable=False)
    risk_nature = Column(String(20))
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.model_id"), nullable=True)
    model_version = Column(String(50), nullable=False)
    data_vintage = Column(DateTime(timezone=True), nullable=False)
    shap_factors = Column(JSONB)
    observation_ids = Column(ARRAY(UUID(as_uuid=True)))
    valid_from = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    valid_to = Column(DateTime(timezone=True))
    scored_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    # ── Sprint 5: Scoring Engine IP columns ──────────────────────
    score_ci_lower           = Column(Numeric)          # ensemble 10th percentile
    score_ci_upper           = Column(Numeric)          # ensemble 90th percentile
    score_velocity_6h        = Column(Numeric)          # dScore/dt over 6 hours
    score_velocity_24h       = Column(Numeric)          # dScore/dt over 24 hours
    score_velocity_48h       = Column(Numeric)          # dScore/dt over 48 hours
    ensemble_scores          = Column(JSONB)            # {xgb: N, lgbm: N, logistic: N}
    compound_flag            = Column(Boolean)          # cross-hazard compound event active
    regulatory_fingerprint   = Column(Text)             # SHA-256 of all inputs


class SatelliteObservation(Base):
    __tablename__ = "satellite_observations"

    observation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    h3_cell = Column(String(20), nullable=False)
    h3_resolution = Column(SmallInteger, nullable=False, default=8)
    source_provider = Column(String(100), nullable=False)
    hazard_type = Column(String(50), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    raw_value = Column(Numeric)
    raw_unit = Column(String(50))
    quality_flag = Column(SmallInteger, nullable=False, default=0)
    quality_notes = Column(Text)
    cog_uri = Column(Text)
    adapter_version = Column(String(50), nullable=False)


class MLFeatureFlood(Base):
    """Feature store for flood model. One row per H3 cell per observation timestamp."""
    __tablename__ = "ml_features_flood"
    __table_args__ = (
        PrimaryKeyConstraint("feature_id", "observed_at"),
    )

    feature_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    h3_cell = Column(String(20), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    # SAR features
    sar_backscatter_db = Column(Numeric)
    backscatter_anomaly_7d = Column(Numeric)
    # GloFAS features
    glofas_discharge_m3s = Column(Numeric)
    discharge_vs_return_2yr = Column(Numeric)
    # Terrain features (static — from DEM)
    dem_elevation_m = Column(Numeric)
    dem_slope_degrees = Column(Numeric)
    distance_to_water_km = Column(Numeric)
    # ERA5 / weather features
    soil_saturation_index = Column(Numeric)
    precipitation_7d_mm = Column(Numeric)
    era5_historical_flood_freq = Column(Numeric)
    # Ground truth label (populated by Outcome Feedback Service)
    flood_occurred = Column(Boolean)
    label_source = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class MLFeatureHeat(Base):
    """Feature store for heat model."""
    __tablename__ = "ml_features_heat"
    __table_args__ = (
        PrimaryKeyConstraint("feature_id", "observed_at"),
    )

    feature_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    h3_cell = Column(String(20), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    lst_kelvin = Column(Numeric)
    lst_anomaly_vs_baseline = Column(Numeric)
    era5_temp_2m_c = Column(Numeric)
    era5_temp_30yr_mean = Column(Numeric)
    era5_temp_trend_per_decade = Column(Numeric)
    urban_heat_island_factor = Column(Numeric)
    population_density = Column(Numeric)
    days_above_35c_ytd = Column(Integer)
    # Labels
    heat_event_occurred = Column(Boolean)
    label_source = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class MLFeatureWildfire(Base):
    """Feature store for wildfire model."""
    __tablename__ = "ml_features_wildfire"
    __table_args__ = (
        PrimaryKeyConstraint("feature_id", "observed_at"),
    )

    feature_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    h3_cell = Column(String(20), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    firms_frp_mw = Column(Numeric)
    firms_confidence_pct = Column(Integer)
    effis_fire_weather_index = Column(Numeric)
    ndvi_index = Column(Numeric)
    ndvi_anomaly_vs_baseline = Column(Numeric)
    gfs_wind_speed_ms = Column(Numeric)
    gfs_relative_humidity_pct = Column(Numeric)
    days_since_last_rain = Column(Integer)
    # Labels
    fire_occurred = Column(Boolean)
    label_source = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class CustomerLocation(Base):
    __tablename__ = "customer_locations"

    location_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    location_name = Column(String(500))
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    h3_cell_r8 = Column(String(20))
    h3_cell_r7 = Column(String(20))
    asset_type = Column(String(100))
    asset_value = Column(Numeric(18, 2))
    currency = Column(String(3))
    registered_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    is_active = Column(Boolean, nullable=False, default=True)


class AlertConfig(Base):
    __tablename__ = "alert_configs"

    config_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("customer_locations.location_id"))
    hazard_type = Column(String(50), nullable=False)
    scenario = Column(String(50), nullable=False, default="baseline")
    alert_threshold = Column(Numeric(5, 2), nullable=False)
    notification_channels = Column(JSONB, nullable=False)
    maker_user_id = Column(String(255))
    maker_at = Column(DateTime(timezone=True))
    checker_user_id = Column(String(255))
    checker_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, nullable=False, default=False)
    activated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    alert_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(UUID(as_uuid=True), ForeignKey("alert_configs.config_id"), nullable=False)
    score_id = Column(UUID(as_uuid=True), nullable=False)
    h3_cell = Column(String(20), nullable=False)
    hazard_type = Column(String(50), nullable=False)
    canonical_score = Column(Numeric(5, 2), nullable=False)
    alert_threshold = Column(Numeric(5, 2), nullable=False)
    fired_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    notification_status = Column(JSONB)


class ParametricContract(Base):
    __tablename__ = "parametric_contracts"

    contract_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    contract_ref = Column(String(100), nullable=False, unique=True)
    hazard_type = Column(String(50), nullable=False)
    coverage_h3_cells = Column(ARRAY(String))
    trigger_threshold = Column(Numeric(5, 2), nullable=False)
    payout_currency = Column(String(3), nullable=False)
    payout_amount = Column(Numeric(18, 2), nullable=False)
    contract_start = Column(Date, nullable=False)
    contract_end = Column(Date, nullable=False)
    webhook_endpoint = Column(Text, nullable=False)
    maker_user_id = Column(String(255), nullable=False)
    maker_at = Column(DateTime(timezone=True), nullable=False)
    checker_user_id = Column(String(255), nullable=False)
    checker_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    activated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class TriggerEvent(Base):
    """Immutable. DB-level rules prevent UPDATE and DELETE."""
    __tablename__ = "trigger_events"

    trigger_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("parametric_contracts.contract_id"), nullable=False)
    score_id = Column(UUID(as_uuid=True), nullable=False)
    h3_cell = Column(String(20), nullable=False)
    hazard_type = Column(String(50), nullable=False)
    canonical_score = Column(Numeric(5, 2), nullable=False)
    trigger_threshold = Column(Numeric(5, 2), nullable=False)
    observation_ids = Column(ARRAY(UUID(as_uuid=True)))
    shap_factors = Column(JSONB, nullable=False)
    model_version = Column(String(50), nullable=False)
    fired_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    webhook_status = Column(String(50))
    webhook_response = Column(JSONB)


class RegulatoryPackage(Base):
    """Immutable after is_released=True."""
    __tablename__ = "regulatory_packages"

    package_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), nullable=False)
    framework = Column(String(50), nullable=False)
    reporting_period_start = Column(Date, nullable=False)
    reporting_period_end = Column(Date, nullable=False)
    score_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    model_version = Column(String(50), nullable=False)
    methodology_doc_uri = Column(Text, nullable=False)
    package_data = Column(JSONB, nullable=False)
    maker_user_id = Column(String(255), nullable=False)
    maker_at = Column(DateTime(timezone=True), nullable=False)
    checker_user_id = Column(String(255))
    checker_at = Column(DateTime(timezone=True))
    is_released = Column(Boolean, nullable=False, default=False)
    released_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class OutcomeFeedback(Base):
    __tablename__ = "outcome_feedback"

    feedback_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    score_id = Column(UUID(as_uuid=True), nullable=False)
    h3_cell = Column(String(20), nullable=False)
    hazard_type = Column(String(50), nullable=False)
    predicted_score = Column(Numeric(5, 2), nullable=False)
    predicted_bucket = Column(String(5), nullable=False)
    event_occurred = Column(Boolean, nullable=False)
    confirmed_intensity = Column(Numeric)
    intensity_unit = Column(String(50))
    outcome_source = Column(String(100), nullable=False)
    outcome_observed_at = Column(DateTime(timezone=True), nullable=False)
    prediction_lead_days = Column(Integer)
    recorded_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    table_name = Column(String(100), nullable=False)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(50), nullable=False)
    performed_by = Column(String(255), nullable=False)
    performed_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    details = Column(JSONB)


class SeismicEvent(Base):
    """
    Normalised earthquake event catalog from EMSC, USGS, INGV.
    Append-only; used to track mainshocks and trigger damage assessments.
    """
    __tablename__ = "seismic_events"

    event_id = Column(Text, primary_key=True)
    magnitude = Column(Numeric(4, 2), nullable=False)
    mag_type = Column(String(10))  # 'Mw', 'ML', 'mb'
    depth_km = Column(Numeric(7, 2))
    epicentre_lat = Column(Numeric(8, 5), nullable=False)
    epicentre_lon = Column(Numeric(8, 5), nullable=False)
    epicentre_h3 = Column(String(20))
    origin_time = Column(DateTime(timezone=True), nullable=False)
    region_name = Column(Text)
    source_catalog = Column(String(50))  # 'EMSC', 'USGS', 'INGV'
    review_status = Column(String(20))  # 'reviewed', 'preliminary', 'automatic'
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    damage_assessment_status = Column(String(30))  # 'pending', 'complete', 'insufficient_data'

    # Relationships
    damage_assessments = relationship("DamageAssessment", back_populates="event")


class DamageAssessment(Base):
    """
    Post-event SAR damage assessment results (M≥5.0 earthquakes).
    One row per (event × H3 cell) with damage probability from SAR intensity change.
    """
    __tablename__ = "damage_assessments"
    __table_args__ = (
        UniqueConstraint("event_id", "h3_cell", name="uq_damage_event_cell"),
    )

    assessment_id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Text, ForeignKey("seismic_events.event_id", ondelete="CASCADE"), nullable=False)
    h3_cell = Column(String(20), nullable=False)
    damage_probability = Column(Numeric(5, 4), nullable=False)  # 0.0000–1.0000
    log_ratio_db = Column(Numeric(8, 4))  # dB change pre→post SAR
    confidence = Column(String(10))  # 'high', 'medium', 'low'
    distance_km = Column(Numeric(7, 2))  # from epicentre
    method = Column(String(50))  # 'sar_intensity_change_grd'
    pre_pass_time = Column(DateTime(timezone=True))
    post_pass_time = Column(DateTime(timezone=True))
    assessed_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    # Relationships
    event = relationship("SeismicEvent", back_populates="damage_assessments")
