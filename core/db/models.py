"""
SQLAlchemy ORM Models for Climate Intelligence Platform

Regulatory + CRCS (Continuous Regulatory Compliance Service) Complete Models
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
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
    # Average Precision is the honest metric for rare-event models — ROC-AUC is
    # misleading at very low base rates. validation_note carries the caveat
    # (e.g. single-event / proxy labels / forecasting untested).
    validation_avg_precision = Column(Numeric(6, 5))
    validation_note = Column(Text)
    is_active = Column(Boolean, nullable=False, default=False)
    activated_at = Column(DateTime(timezone=True))
    activated_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    # ── governance lifecycle (MLOps) ──────────────────────────────────────────────────────────────
    # candidate → approved → active → retired, with an optional challenger running beside the active one.
    # A version can only be APPROVED once its out-of-sample calibration clears the publish gate (r² ≥ 0.40) —
    # the same honesty gate the product publishes on, now enforced as a promotion control. Every transition is
    # recorded append-only in model_status_event (audit + rollback trail); superseded_by links to the version
    # that replaced this one, so a rollback is just re-activating a prior model_id.
    lifecycle_status = Column(String(20), nullable=False, default="candidate")
    r2_oos = Column(Numeric(5, 4))              # out-of-sample calibration r² (the publish-gate metric)
    calibration_note = Column(Text)
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(String(255))
    retired_at = Column(DateTime(timezone=True))
    superseded_by = Column(UUID(as_uuid=True))  # the model_id that replaced this one (rollback lineage)


class ModelStatusEvent(Base):
    """Append-only lifecycle audit for the model registry — every promotion/rollback/drift-driven change.

    This is the governance trail: who moved which model version from what status to what, why, and the
    calibration it carried at the time. Never updated or deleted — a rollback is a NEW event, not a rewrite.
    """
    __tablename__ = "model_status_event"

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.model_id"), nullable=False)
    hazard_type = Column(String(50), nullable=False)
    from_status = Column(String(20))
    to_status = Column(String(20), nullable=False)
    actor = Column(String(255))
    reason = Column(Text)
    r2_oos = Column(Numeric(5, 4))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ModelDriftObservation(Base):
    """Append-only drift monitoring against the active model's baseline.

    `kind` = input (feature distribution, e.g. PSI) · prediction (score distribution shift) ·
    calibration (r² decay vs the approved figure). `breached` flags an observation past its threshold,
    which is the trigger to review the active model against a challenger (or roll back).
    """
    __tablename__ = "model_drift_observation"

    obs_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.model_id"), nullable=False)
    hazard_type = Column(String(50), nullable=False)
    kind = Column(String(20), nullable=False)      # input | prediction | calibration
    metric = Column(String(40), nullable=False)    # psi | ks | r2_delta | …
    value = Column(Numeric(10, 5), nullable=False)
    threshold = Column(Numeric(10, 5))
    breached = Column(Boolean, nullable=False, default=False)
    drift_window = Column(String(40))   # 'window' is a reserved word in SQL — name it explicitly
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ValidationRun(Base):
    """A backtest result — the append-only, immutable validation track record.

    One row per (model/approach × hazard × scope × horizon) validated against an INDEPENDENT observed
    target. Immutable by DB trigger (no UPDATE/DELETE) so the record is audit-grade: every run carries its
    full provenance (method, target source, sample size, code version, data vintage) and can be reproduced.
    `kind` picks the honest metric family: 'regression' (R²-gated) vs 'discrimination' (rank/AUC-gated).
    """
    __tablename__ = "validation_run"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id = Column(UUID(as_uuid=True), ForeignKey("model_registry.model_id"))  # nullable: approach not yet registered
    hazard_type = Column(String(50), nullable=False)
    scope = Column(String(80))                 # region / commodity / 'global'
    horizon = Column(String(20))               # 'current' / '2050' / … (nullable)
    kind = Column(String(20), nullable=False)  # regression | discrimination
    method = Column(String(30), nullable=False)  # in_sample | out_of_sample | temporal_holdout
    target_source = Column(String(120), nullable=False)  # the independent truth (EMSC / IBTrACS / FAO / …)
    n_samples = Column(Integer, nullable=False)
    metrics = Column(JSONB, nullable=False)    # r2, spearman, auc, rmse, mae, bias, brier, bands, …
    skill_grade = Column(String(20), nullable=False)  # strong | fair | weak | insufficient
    passed_gate = Column(Boolean, nullable=False)
    gate = Column(String(60))                  # which gate was applied
    notes = Column(Text)
    code_version = Column(String(60))
    data_vintage = Column(String(60))
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)


class ValidationSample(Base):
    """Per-sample (predicted, observed) pairs behind a run — full drill-down for auditors. Append-only.

    Optional: a run can store aggregate metrics only, or persist every sample for complete traceability."""
    __tablename__ = "validation_sample"

    sample_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("validation_run.run_id"), nullable=False)
    label = Column(String(120))                # cell / event / commodity id
    predicted = Column(Numeric(12, 4))
    observed = Column(Numeric(12, 4))
    meta = Column(JSONB)


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


class MLFeatureDrought(Base):
    """Feature store for the drought model. Completes the declared-but-missing
    drought hazard substrate (Tier 2), mirroring flood/heat/wildfire."""
    __tablename__ = "ml_features_drought"
    __table_args__ = (
        PrimaryKeyConstraint("feature_id", "observed_at"),
    )

    feature_id = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    h3_cell = Column(String(20), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    # Standardised drought indices
    spi_3month = Column(Numeric)               # Standardized Precipitation Index
    spei_3month = Column(Numeric)              # SPI adjusted for evapotranspiration
    soil_moisture_percentile = Column(Numeric)
    precipitation_deficit_mm = Column(Numeric)
    evapotranspiration_mm = Column(Numeric)
    # Vegetation stress
    ndvi_index = Column(Numeric)
    ndvi_anomaly_vs_baseline = Column(Numeric)
    # Atmospheric
    era5_temp_anomaly_c = Column(Numeric)
    days_since_significant_rain = Column(Integer)
    reservoir_storage_pct = Column(Numeric)
    # Label (populated by Outcome Feedback Service)
    drought_occurred = Column(Boolean)
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


class SourceSystem(Base):
    """A customer's external system of record (GL / core-banking, loan-origination, data warehouse, GIS),
    registered so a user can drill from a Tellumen figure through to the SOURCE record. Phase 1 is deep-link
    only: the external app renders the record under its own auth; Tellumen stores no source data, only the
    link template. (Phase 2 = read-through data-pull, which additionally needs identity federation.)"""

    __tablename__ = "source_systems"

    source_system_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    key = Column(String(64), nullable=False)          # stable handle, e.g. 'core_banking'
    name = Column(String(120), nullable=False)         # display, e.g. 'Finacle core banking'
    kind = Column(String(40), nullable=False, default="other")  # gl/core_banking/los/warehouse/gis/other
    deep_link_template = Column(Text, nullable=False)  # 'https://gl.example.com/account/{id}' — {id}=source_record_id
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("org_id", "key", name="uq_source_system_org_key"),)


class EntitySourceRef(Base):
    """Links one Tellumen entity (a loan / policy / property / plot row) to its record id in a registered
    source system — the pointer that makes drill-through possible. Additive; stores only the id, no source data."""

    __tablename__ = "entity_source_refs"

    ref_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)   # portfolio_entities.entity_id (or sector equivalent)
    source_system_key = Column(String(64), nullable=False)
    source_record_id = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)

    __table_args__ = (UniqueConstraint("org_id", "entity_id", "source_system_key", name="uq_entity_source_ref"),)
