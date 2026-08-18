"""
SQLAlchemy ORM Models - REGULATORY & CRCS COMPLETE

All 30+ model classes for:
- Multi-tenancy (Organization, User)
- Assets & Climate Exposure
- Regulatory Frameworks & Versioning
- Change Detection (CRCS)
- Climate Scenarios & Financial Modeling
- GHG Emissions & Metrics
- Risk Scoring
- Filings & Compliance
- Subscriptions
- Archive & Retention
- Audit & Governance

This file should be imported as:
from core.db.models_regulatory_complete import *
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Column, Date, DateTime,
    ForeignKey, Integer, Numeric, PrimaryKeyConstraint, Index,
    String, Text, UniqueConstraint, func, DECIMAL, JSON, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

# Single source of truth: the bank-vertical tables share the platform's
# declarative Base, so one metadata describes the whole schema and Alembic can
# build all of it. (Previously this module had its own Base, invisible to
# env.py — which is why the bank tables only existed in a hand-written .sql.)
from core.db.models import Base


def utcnow():
    return datetime.now(timezone.utc)


# ============================================================================
# MULTI-TENANCY & CORE ENTITIES
# ============================================================================

class Organization(Base):
    __tablename__ = 'organizations'

    org_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    type = Column(String(50), nullable=False)  # 'bank', 'insurer', 'asset_manager'
    country = Column(String(2), nullable=False)
    aum_eur = Column(DECIMAL(18, 2))
    employees = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    users = relationship('User', back_populates='organization', cascade='all, delete-orphan')
    assets = relationship('BankAsset', back_populates='organization', cascade='all, delete-orphan')
    emissions = relationship('GHGEmissionsInventory', back_populates='organization', cascade='all, delete-orphan')
    filings = relationship('RegulatoryFiling', back_populates='organization', cascade='all, delete-orphan')
    crcs_subscription = relationship('OrgCRCSSubscription', back_populates='organization', uselist=False)
    module_subscriptions = relationship('OrgModuleSubscription', back_populates='organization', cascade='all, delete-orphan')
    preference = relationship('OrgRegulationVersionPreference', back_populates='organization', uselist=False)


class User(Base):
    __tablename__ = 'users'

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False)  # 'admin', 'analyst', 'reporter', 'viewer'
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint('org_id', 'email'),)

    organization = relationship('Organization', back_populates='users')


# ============================================================================
# ASSETS & CLIMATE EXPOSURE
# ============================================================================

class BankAsset(Base):
    __tablename__ = 'bank_assets'

    asset_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    asset_name = Column(String(255), nullable=False)
    asset_type = Column(String(50), nullable=False)
    latitude = Column(DECIMAL(10, 6))
    longitude = Column(DECIMAL(10, 6))
    h3_cell = Column(String(20))
    region = Column(String(100))
    country = Column(String(2))
    asset_value_eur = Column(DECIMAL(18, 2))
    annual_revenue_eur = Column(DECIMAL(18, 2))
    construction_year = Column(Integer)
    expected_lifespan_years = Column(Integer)
    sector = Column(String(100))
    nace_code = Column(String(10))
    gics_code = Column(String(10))
    taxonomy_status = Column(String(50))
    taxonomy_activity = Column(String(255))
    dnsh_assessment = Column(JSONB)
    energy_consumption_mwh = Column(DECIMAL(15, 2))
    ghg_emissions_scope1_tco2e = Column(DECIMAL(15, 2))
    ghg_emissions_scope2_tco2e = Column(DECIMAL(15, 2))
    ghg_emissions_scope3_tco2e = Column(DECIMAL(15, 2))
    carbon_intensity_tco2e_per_meur = Column(DECIMAL(10, 2))
    insurance_coverage_eur = Column(DECIMAL(18, 2))
    insurance_coverage_pct = Column(DECIMAL(5, 2))
    resilience_rating = Column(String(10))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    data_source = Column(String(100))

    __table_args__ = (
        UniqueConstraint('org_id', 'asset_id'),
        Index('idx_bank_assets_org_location', 'org_id', 'h3_cell'),
        Index('idx_bank_assets_org_sector', 'org_id', 'sector'),
        Index('idx_bank_assets_timestamp', 'org_id', 'created_at'),
    )

    organization = relationship('Organization', back_populates='assets')
    hazard_exposures = relationship('ClimateHazardExposure', back_populates='asset', cascade='all, delete-orphan')
    scenario_impacts = relationship('ScenarioFinancialImpact', back_populates='asset', cascade='all, delete-orphan')
    emissions = relationship('GHGEmissionsInventory', back_populates='asset', cascade='all, delete-orphan')
    risk_scores = relationship('ClimateRiskScore', back_populates='asset', cascade='all, delete-orphan')


class ClimateHazardExposure(Base):
    """
    Bank-vertical physical risk exposure per asset × hazard.

    NOTE (reconciliation #1): `physical_risk_score` is DEPRECATED as an
    independently stored value. The source of truth for an asset's physical
    risk is `canonical_scores`, projected by H3 cell. Read it via the
    `v_bank_asset_physical_risk` view or
    `services.intelligence.asset_risk_projection.project_org_assets()`, not from
    this column. The column is retained only for backfill/transition and will be
    dropped once all readers use the projection.
    """
    __tablename__ = 'climate_hazard_exposure'

    exposure_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey('bank_assets.asset_id', ondelete='CASCADE'), nullable=False)
    hazard_type = Column(String(50), nullable=False)
    exposure_level = Column(String(20))
    physical_risk_score = Column(DECIMAL(5, 2))  # DEPRECATED — project from canonical_scores
    hazard_probability_pct = Column(DECIMAL(5, 2))
    hazard_intensity = Column(DECIMAL(10, 2))
    expected_annual_loss_eur = Column(DECIMAL(15, 2))
    conditional_var_95_eur = Column(DECIMAL(15, 2))
    revenue_impact_pct = Column(DECIMAL(5, 2))
    capex_adaptation_required_eur = Column(DECIMAL(15, 2))
    eu_taxonomy_physical_resilience = Column(DECIMAL(5, 2))
    basel_physical_risk_weight_pct = Column(DECIMAL(5, 2))
    scenario_1_5c_probability_pct = Column(DECIMAL(5, 2))
    scenario_2c_probability_pct = Column(DECIMAL(5, 2))
    scenario_4c_probability_pct = Column(DECIMAL(5, 2))
    assessment_date = Column(Date)
    assessment_model = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'asset_id', 'hazard_type'),
        Index('idx_hazard_org_type', 'org_id', 'hazard_type'),
        Index('idx_hazard_org_risk', 'org_id', 'physical_risk_score'),
    )

    asset = relationship('BankAsset', back_populates='hazard_exposures')


# ============================================================================
# REGULATORY FRAMEWORKS & VERSIONING
# ============================================================================

class RegulatoryFramework(Base):
    __tablename__ = 'regulatory_frameworks'

    framework_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    framework_name = Column(String(100), nullable=False, unique=True)
    framework_region = Column(String(50))
    mandatory_effective_date = Column(Date)
    enforcing_body = Column(String(100))
    penalty_mechanism = Column(String(255))
    reporting_format = Column(String(100))
    reporting_frequency = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    versions = relationship('RegulationVersion', back_populates='framework', cascade='all, delete-orphan')
    changes = relationship('RegulatoryChange', back_populates='framework', cascade='all, delete-orphan')
    filings = relationship('RegulatoryFiling', back_populates='framework')


class RegulationVersion(Base):
    __tablename__ = 'regulation_versions'

    version_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    framework_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_frameworks.framework_id'), nullable=False)
    version_number = Column(String(50), nullable=False)
    version_label = Column(String(100))
    published_date = Column(Date)
    effective_date = Column(Date)
    end_of_life_date = Column(Date)
    support_status = Column(String(50))  # 'Current', 'Legacy', 'End of Life'
    is_current = Column(Boolean, default=False)
    schema_snapshot = Column(JSONB)
    processing_logic_version = Column(String(50))
    output_format_version = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint('framework_id', 'version_number'),)

    framework = relationship('RegulatoryFramework', back_populates='versions')
    org_preferences = relationship('OrgRegulationVersionPreference', back_populates='version', foreign_keys='OrgRegulationVersionPreference.active_version_id')


class OrgRegulationVersionPreference(Base):
    __tablename__ = 'org_regulation_version_preference'

    preference_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id'), nullable=False)
    framework_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_frameworks.framework_id'), nullable=False)
    active_version_id = Column(UUID(as_uuid=True), ForeignKey('regulation_versions.version_id'))
    previous_version_id = Column(UUID(as_uuid=True), ForeignKey('regulation_versions.version_id'))
    immutability_rule = Column(String(50))  # 'immutable', 'mutable'
    version_switched_date = Column(DateTime(timezone=True))
    end_of_support_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint('org_id', 'framework_id'),)

    organization = relationship('Organization', back_populates='preference')
    version = relationship('RegulationVersion', back_populates='org_preferences', foreign_keys=[active_version_id])


class AnalyticsSavedView(Base):
    """A user-defined 'custom view' over the forward-looking exposure analytics — a saved parameter set
    (scope × measure × scenario × horizon × group-by). It stores ONLY PARAMETERS, never numbers: every
    figure is recomputed live from the golden source, so a saved view can never carry a stale or invented
    value, and is always exploratory (never a frozen/filed figure). Private by default; is_shared exposes it
    read-only to the rest of the org; only the creator can edit or delete it."""
    __tablename__ = 'analytics_saved_view'

    view_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=False)   # users.user_id (no FK: a view outlives user cleanup)
    name = Column(String(120), nullable=False)
    config = Column(JSONB, nullable=False)   # {scope, measure, scenario, horizon, groupBy, threshold, chart}
    is_shared = Column(Boolean, nullable=False, server_default='false')
    is_pinned = Column(Boolean, nullable=False, server_default='false')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index('idx_analytics_view_org', 'org_id'),)


class KriBreachEpisode(Base):
    """One BREACH RUN of a key risk indicator — the append-only spine for detection lag.

    A KRI is graded live against its appetite band, but 'how long was it in breach before anyone acted?'
    needs a persisted history of WHEN the breach began. This table is that history: services.governance.
    kri_monitor.observe() opens an episode the first time a KRI is seen out of appetite (onset_at), keeps
    the worst value seen (peak_value) while it stays breached, stamps acknowledged_at the moment a human
    raises a remediation task, and closes it (cleared_at) when the KRI returns within appetite. At most one
    OPEN episode per (org, framework, kri) is enforced at the database. Detection/response lag is then a pure
    timestamp subtraction over real observations — never a guess."""
    __tablename__ = 'kri_breach_episode'

    episode_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    framework = Column(String(60), nullable=False)
    kri_key = Column(String(80), nullable=False)
    label = Column(String(200))
    severity = Column(String(10), nullable=False)       # worst grade seen this run: 'amber' | 'red'
    direction = Column(String(20))                      # higher_worse | lower_worse (which way is bad)
    onset_value = Column(Numeric)                       # the value when first observed in breach
    peak_value = Column(Numeric)                        # the worst value seen during the run
    threshold = Column(Numeric)                         # the band edge it crossed
    onset_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())  # last eval still in breach
    acknowledged_at = Column(DateTime(timezone=True))   # first human action (remediation task raised)
    acknowledged_by = Column(UUID(as_uuid=True))
    cleared_at = Column(DateTime(timezone=True))        # returned within appetite (NULL = still open)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index('idx_kri_episode_lookup', 'org_id', 'framework', 'kri_key'),
        # at most one OPEN episode per indicator — the invariant the monitor relies on
        Index('uq_kri_episode_open', 'org_id', 'framework', 'kri_key', unique=True,
              postgresql_where=text('cleared_at IS NULL')),
    )


class NotifiableEvent(Base):
    """A regulatory-NOTIFICATION obligation with a statutory clock — the 'notify the regulator within N hours'
    workflow that a calendar cadence can't hold. A human flags a breach/incident as notifiable; this records
    when it arose, the window, and therefore when it is DUE, tracks it to overdue, and captures the record of
    what was actually sent (reference, to whom, when). Deliberately not auto-fired for every appetite breach:
    which events are notifiable is a jurisdiction-specific compliance judgement, so raising one is an explicit
    act, and the mechanism (clock, overdue, evidence) is what the platform owns."""
    __tablename__ = 'notifiable_event'

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    source_type = Column(String(30), nullable=False)   # 'kri_breach' | 'exception' | 'incident' | 'manual'
    source_ref = Column(String(160))                   # e.g. 'bank_tcfd:pct_at_risk' — for de-dupe
    title = Column(String(240), nullable=False)
    category = Column(String(40))                      # 'material_breach' | 'incident' | 'other'
    severity = Column(String(10))
    authority = Column(String(120))                    # who must be notified (regulator label)
    arose_at = Column(DateTime(timezone=True), nullable=False)     # when the underlying event arose (e.g. onset)
    window_hours = Column(Integer, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)       # arose_at + window
    status = Column(String(12), nullable=False, server_default='open')  # open | notified | dismissed
    notified_at = Column(DateTime(timezone=True))
    notified_ref = Column(String(160))                 # the regulator's ack / submission reference
    notified_to = Column(String(200))
    notified_by = Column(UUID(as_uuid=True))
    assignee_user_id = Column(UUID(as_uuid=True))
    dismiss_reason = Column(Text)
    created_by = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('idx_notifiable_org_status', 'org_id', 'status'),
        Index('uq_notifiable_open_source', 'org_id', 'source_type', 'source_ref', unique=True,
              postgresql_where=text("status = 'open'")),
    )


class GlBalance(Base):
    """A general-ledger control-account balance, as provided by the customer's finance system — the missing
    half of gate 4 'reconcile to the ledger'. The platform already ties a reported figure to its golden
    source; this lets it also tie the reported book TOTAL back to the GL, so a variance surfaces here rather
    than in an examination. Uploaded in dated batches (one CSV = one batch); reconciliation uses the latest
    batch. `control_for` tags which reported line an account backs (e.g. 'book')."""
    __tablename__ = 'gl_balance'

    gl_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    account_code = Column(String(60), nullable=False)
    account_name = Column(String(200))
    balance_eur = Column(Numeric, nullable=False)
    control_for = Column(String(40))                   # which reported line this account backs, e.g. 'book'
    as_of_date = Column(Date)
    uploaded_by = Column(UUID(as_uuid=True))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index('idx_gl_balance_org_batch', 'org_id', 'batch_id'),)


class LoanArrears(Base):
    """Per-loan arrears for the agricultural book — the input to the seasonal-arrears overlay.

    Agricultural income is seasonal, so a post-harvest carry-over past-due is NOT the same signal as genuine
    deterioration; treating it as default over-states the risk. This holds the customer-provided days-past-due
    (with the loan's crop & region), and services.governance.seasonal_arrears classifies each past-due loan as
    'seasonal carry-over' or 'genuine' against a documented crop calendar. It is an explainable MANAGEMENT
    OVERLAY the accountable person can defend — not a replacement for IFRS-9 staging."""
    __tablename__ = 'loan_arrears'

    arrears_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    batch_id = Column(UUID(as_uuid=True), nullable=False)
    loan_ref = Column(String(80), nullable=False)
    borrower_name = Column(String(200))
    crop = Column(String(60))
    region = Column(String(120))
    exposure_eur = Column(Numeric)
    days_past_due = Column(Integer, nullable=False)
    as_of_date = Column(Date)
    uploaded_by = Column(UUID(as_uuid=True))
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index('idx_loan_arrears_org_batch', 'org_id', 'batch_id'),)


class CommodityPriceIndex(Base):
    """Observed authoritative commodity / farm-input price indices (FAO Food Price Index, World Bank 'Pink
    Sheet', USDA) — reference market data, not a Tellumen forecast. Loaded via the same ingest path from the
    published agency series. Feeds the book-weighted price-pressure view: a rising index on a commodity the
    buyer sources is input-cost pressure on the bill of materials. One value per (source, commodity, month)."""
    __tablename__ = 'commodity_price_index'

    price_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(60), nullable=False)        # 'FAO_FPI' | 'WorldBank_PinkSheet' | 'USDA' | 'sample'
    commodity = Column(String(60), nullable=False)     # normalised lower-case
    period_ym = Column(String(7), nullable=False)      # 'YYYY-MM'
    index_value = Column(Numeric, nullable=False)
    unit = Column(String(40))                          # e.g. 'index 2014-16=100' | 'USD/tonne'
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('source', 'commodity', 'period_ym', name='uq_price_source_commodity_period'),
        Index('idx_price_commodity_period', 'commodity', 'period_ym'),
    )


# ============================================================================
# REGULATORY CHANGE DETECTION (CRCS)
# ============================================================================

class RegulatoryChange(Base):
    __tablename__ = 'regulatory_changes'

    change_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    framework_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_frameworks.framework_id'), nullable=False)
    old_version = Column(String(50))
    new_version = Column(String(50))
    change_source = Column(String(100))
    source_document_url = Column(Text)
    source_document_text = Column(JSONB)
    detection_method = Column(String(50))
    detected_date = Column(DateTime(timezone=True))
    detected_by_system = Column(Boolean, default=True)
    confirmed_date = Column(DateTime(timezone=True))
    confirmed_by = Column(String(255))
    publication_date = Column(Date)
    official_effective_date = Column(Date)
    implementation_deadline = Column(Date)
    change_type = Column(String(50))
    change_classification = Column(String(50))  # 'Change' or 'Module'
    affected_tables = Column(JSONB)
    affected_processing_modules = Column(JSONB)
    affected_outputs = Column(JSONB)
    breaking_change = Column(Boolean)
    backward_compatible = Column(Boolean)
    data_migration_required = Column(Boolean)
    estimated_dev_hours = Column(Integer)
    estimated_test_hours = Column(Integer)
    estimated_total_hours = Column(Integer)
    estimated_release_date = Column(Date)
    customer_deadline = Column(Date)
    urgency_flag = Column(Boolean)
    status = Column(String(50))  # 'Detected', 'Confirmed', 'In Development', etc.
    status_updated_at = Column(DateTime(timezone=True), server_default=func.now())
    is_new_module = Column(Boolean)
    module_name = Column(String(255))
    module_pricing_tier = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('framework_id', 'old_version', 'new_version'),
        Index('idx_regulatory_changes_status', 'status'),
        Index('idx_regulatory_changes_deadline', 'implementation_deadline'),
    )

    framework = relationship('RegulatoryFramework', back_populates='changes')
    details = relationship('RegulatoryChangeDetail', back_populates='change', cascade='all, delete-orphan')


class RegulatoryChangeDetail(Base):
    __tablename__ = 'regulatory_change_details'

    detail_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    change_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_changes.change_id', ondelete='CASCADE'), nullable=False)
    article_or_section = Column(String(255))
    old_requirement = Column(Text)
    new_requirement = Column(Text)
    requirement_changed = Column(Text)
    affects_data_model = Column(Boolean)
    data_field_name = Column(String(255))
    field_type_change = Column(String(100))
    affects_processing_logic = Column(Boolean)
    processing_change_description = Column(Text)
    calculation_methodology_changed = Column(Boolean)
    affects_output_format = Column(Boolean)
    output_change_description = Column(Text)
    mitigation_strategy = Column(Text)
    breaking_change_mitigation = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    change = relationship('RegulatoryChange', back_populates='details')


# ============================================================================
# CLIMATE SCENARIOS & FINANCIAL MODELING
# ============================================================================

class ClimateScenario(Base):
    __tablename__ = 'climate_scenarios'

    scenario_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scenario_name = Column(String(100), nullable=False)
    pathway = Column(String(20), nullable=False, unique=True)  # '1.5c', '2c', '4c'
    temperature_increase_celsius = Column(DECIMAL(5, 2))
    carbon_price_eur_per_ton_2030 = Column(DECIMAL(10, 2))
    carbon_price_eur_per_ton_2050 = Column(DECIMAL(10, 2))
    renewable_energy_cost_decline_pct_2030 = Column(DECIMAL(5, 2))
    electric_vehicle_adoption_pct_2030 = Column(DECIMAL(5, 2))
    energy_efficiency_improvement_pct = Column(DECIMAL(5, 2))
    short_term_year = Column(Integer)
    medium_term_year = Column(Integer)
    long_term_year = Column(Integer)
    scenario_source = Column(String(100))
    baseline_year = Column(Integer, default=2024)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    financial_impacts = relationship('ScenarioFinancialImpact', back_populates='scenario', cascade='all, delete-orphan')


class ScenarioFinancialImpact(Base):
    __tablename__ = 'scenario_financial_impact'

    impact_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey('bank_assets.asset_id', ondelete='CASCADE'), nullable=False)
    scenario_id = Column(UUID(as_uuid=True), ForeignKey('climate_scenarios.scenario_id', ondelete='CASCADE'), nullable=False)
    time_horizon = Column(String(20), nullable=False)
    base_revenue_eur = Column(DECIMAL(18, 2))
    demand_shift_pct = Column(DECIMAL(5, 2))
    price_impact_pct = Column(DECIMAL(5, 2))
    projected_revenue_eur = Column(DECIMAL(18, 2))
    revenue_impact_eur = Column(DECIMAL(18, 2))
    base_opex_eur = Column(DECIMAL(18, 2))
    input_cost_inflation_pct = Column(DECIMAL(5, 2))
    regulatory_compliance_cost_eur = Column(DECIMAL(15, 2))
    adaptation_capex_eur = Column(DECIMAL(15, 2))
    projected_opex_eur = Column(DECIMAL(18, 2))
    opex_impact_eur = Column(DECIMAL(18, 2))
    stranded_asset_risk_pct = Column(DECIMAL(5, 2))
    asset_impairment_eur = Column(DECIMAL(15, 2))
    discount_rate_pct = Column(DECIMAL(5, 2))
    climate_risk_premium_pct = Column(DECIMAL(5, 2))
    net_present_value_eur = Column(DECIMAL(18, 2))
    npv_change_from_base_pct = Column(DECIMAL(5, 2))
    financial_impact_materiality_pct = Column(DECIMAL(5, 2))
    is_material = Column(Boolean)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'asset_id', 'scenario_id', 'time_horizon'),
        Index('idx_scenario_impact_org', 'org_id', 'scenario_id'),
        Index('idx_scenario_impact_material', 'org_id', 'is_material'),
    )

    asset = relationship('BankAsset', back_populates='scenario_impacts')
    scenario = relationship('ClimateScenario', back_populates='financial_impacts')


# ============================================================================
# GHG EMISSIONS & METRICS
# ============================================================================

class GHGEmissionsInventory(Base):
    __tablename__ = 'ghg_emissions_inventory'

    emissions_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey('bank_assets.asset_id', ondelete='CASCADE'))
    scope_1_tco2e = Column(DECIMAL(15, 2), nullable=False)
    scope_2_location_based_tco2e = Column(DECIMAL(15, 2), nullable=False)
    scope_2_market_based_tco2e = Column(DECIMAL(15, 2))
    scope_3_tco2e = Column(DECIMAL(15, 2))
    scope_3_category_1_upstream_tco2e = Column(DECIMAL(15, 2))
    scope_3_category_9_downstream_tco2e = Column(DECIMAL(15, 2))
    emissions_intensity_tco2e_per_meur = Column(DECIMAL(10, 2))
    energy_intensity_kwh_per_unit = Column(DECIMAL(10, 2))
    waci_tco2e_per_meur = Column(DECIMAL(10, 2))
    reporting_year = Column(Integer, nullable=False)
    reporting_date = Column(Date)
    calculation_method = Column(String(100))
    emission_factors_source = Column(String(100))
    assurance_level = Column(String(50))
    assurance_provider = Column(String(255))
    sec_form_10k_scope_1 = Column(DECIMAL(15, 2))
    sec_form_10k_scope_2 = Column(DECIMAL(15, 2))
    sec_form_10k_scope_3 = Column(DECIMAL(15, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'asset_id', 'reporting_year'),
        Index('idx_emissions_org_year', 'org_id', 'reporting_year'),
    )

    organization = relationship('Organization', back_populates='emissions')
    asset = relationship('BankAsset', back_populates='emissions')


# ============================================================================
# CLIMATE RISK SCORES
# ============================================================================

class ClimateRiskScore(Base):
    __tablename__ = 'climate_risk_scores'

    score_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey('bank_assets.asset_id', ondelete='CASCADE'), nullable=False)
    overall_risk_score = Column(DECIMAL(5, 2))
    physical_risk_score = Column(DECIMAL(5, 2))
    transition_risk_score = Column(DECIMAL(5, 2))
    financial_materiality_score = Column(DECIMAL(5, 2))
    regulatory_risk_score = Column(DECIMAL(5, 2))
    risk_category = Column(String(50))
    confidence_level_pct = Column(DECIMAL(5, 2))
    sensitivity_to_carbon_price = Column(DECIMAL(5, 2))
    sensitivity_to_physical_events = Column(DECIMAL(5, 2))
    assessment_date = Column(Date)
    assessment_model_version = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'asset_id', 'assessment_date'),
        Index('idx_risk_scores_org_category', 'org_id', 'risk_category'),
    )

    asset = relationship('BankAsset', back_populates='risk_scores')


# ============================================================================
# REGULATORY FILINGS & OUTPUTS
# ============================================================================

class RegulatoryFiling(Base):
    __tablename__ = 'regulatory_filings'

    filing_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    framework_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_frameworks.framework_id'), nullable=False)
    version_id = Column(UUID(as_uuid=True), ForeignKey('regulation_versions.version_id'))
    filing_type = Column(String(100))
    reporting_period_start = Column(Date)
    reporting_period_end = Column(Date)
    filing_version = Column(Integer, default=1)
    is_amended = Column(Boolean, default=False)
    amended_from_filing_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_filings.filing_id'))
    amendment_reason = Column(Text)
    is_immutable = Column(Boolean)
    status = Column(String(50))  # 'Draft', 'Submitted', 'Accepted', 'Amended'
    submission_date = Column(DateTime(timezone=True))
    filing_content = Column(JSONB)
    narrative_summary = Column(Text)
    certification_date = Column(DateTime(timezone=True))
    certified_by = Column(String(255))
    archive_status = Column(String(50))  # 'Live', 'Legacy Support', 'Archived'
    archive_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'framework_id', 'reporting_period_end'),
        Index('idx_filings_org_status', 'org_id', 'status'),
        Index('idx_filings_org_date', 'org_id', 'submission_date'),
    )

    organization = relationship('Organization', back_populates='filings')
    framework = relationship('RegulatoryFramework', back_populates='filings')
    amendments = relationship('FilingAmendment', back_populates='filing', cascade='all, delete-orphan')


class FilingAmendment(Base):
    __tablename__ = 'filing_amendments'

    amendment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filing_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_filings.filing_id'), nullable=False)
    amendment_version = Column(Integer)
    amendment_date = Column(DateTime(timezone=True))
    amendment_reason = Column(Text)
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    amended_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    filing = relationship('RegulatoryFiling', back_populates='amendments')


# ============================================================================
# SUBSCRIPTIONS & MODULES
# ============================================================================

class OrgCRCSSubscription(Base):
    __tablename__ = 'org_crcs_subscription'

    subscription_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False, unique=True)
    subscription_tier = Column(String(50), default='Continuous Regulatory Compliance Service')
    coverage_description = Column(Text)
    annual_crcs_cost_eur = Column(DECIMAL(15, 2))
    billing_start_date = Column(Date)
    billing_end_date = Column(Date)
    max_frameworks_covered = Column(Integer)
    change_coverage_included = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    organization = relationship('Organization', back_populates='crcs_subscription')


class OrgModuleSubscription(Base):
    __tablename__ = 'org_module_subscriptions'

    module_sub_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    module_id = Column(UUID(as_uuid=True), nullable=False)
    module_name = Column(String(255))
    module_description = Column(Text)
    annual_module_cost_eur = Column(DECIMAL(15, 2))
    billing_start_date = Column(Date)
    billing_end_date = Column(Date)
    status = Column(String(50))  # 'Active', 'Inactive'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint('org_id', 'module_id'),)

    organization = relationship('Organization', back_populates='module_subscriptions')


# ============================================================================
# AUDIT & GOVERNANCE
# ============================================================================

class AuditLog(Base):
    # Renamed from 'audit_log' to resolve a collision with the platform's
    # generic audit_log (core/db/models.py). This one is org/framework-scoped
    # regulatory auditing. Python references use the class, not the table name,
    # so this rename is transparent to callers.
    __tablename__ = 'regulatory_audit_log'

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(UUID(as_uuid=True))
    action = Column(String(50))
    changed_by = Column(String(255))
    change_details = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    framework_context = Column(String(100))
    compliance_relevant = Column(Boolean, default=False)

    __table_args__ = (Index('idx_audit_org_time', 'org_id', 'timestamp'),)


class GovernanceStructure(Base):
    __tablename__ = 'governance_structure'

    governance_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False, unique=True)
    board_committee_with_climate_oversight = Column(String(255))
    climate_risk_owner_title = Column(String(100))
    management_level_owner_title = Column(String(100))
    governance_policy_last_updated = Column(Date)
    climate_risk_discussed_in_board_meetings = Column(Integer)
    climate_risk_integrated_in_strategic_plan = Column(Boolean)
    climate_risk_integrated_in_capital_allocation = Column(Boolean)
    climate_risk_integrated_in_compensation = Column(Boolean)
    governance_disclosure_status = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ============================================================================
# KPI SUMMARY
# ============================================================================

class KPISummary(Base):
    __tablename__ = 'kpi_summary'

    kpi_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    reporting_year = Column(Integer)
    total_scope_1_emissions_tco2e = Column(DECIMAL(15, 2))
    total_scope_2_emissions_tco2e = Column(DECIMAL(15, 2))
    total_scope_3_emissions_tco2e = Column(DECIMAL(15, 2))
    taxonomy_aligned_turnover_pct = Column(DECIMAL(5, 2))
    taxonomy_aligned_capex_pct = Column(DECIMAL(5, 2))
    taxonomy_aligned_opex_pct = Column(DECIMAL(5, 2))
    portfolio_physical_risk_avg_score = Column(DECIMAL(5, 2))
    portfolio_transition_risk_avg_score = Column(DECIMAL(5, 2))
    waci_tco2e_per_meur = Column(DECIMAL(10, 2))
    carbon_footprint_tco2e_per_meur = Column(DECIMAL(10, 2))
    portfolio_npv_under_1_5c_scenario_eur = Column(DECIMAL(18, 2))
    portfolio_npv_under_2c_scenario_eur = Column(DECIMAL(18, 2))
    portfolio_npv_under_4c_scenario_eur = Column(DECIMAL(18, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint('org_id', 'reporting_year'),)


# ============================================================================
# ALERTS & REAL-TIME NOTIFICATIONS (PHASE 2)
# ============================================================================

class RegulatoryAlert(Base):
    __tablename__ = 'regulatory_alerts'

    alert_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    change_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_changes.change_id', ondelete='CASCADE'))
    framework_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_frameworks.framework_id'), nullable=False)

    # Org-specific impact
    affected_asset_count = Column(Integer, default=0)
    total_assets = Column(Integer)
    portfolio_value_affected_eur = Column(DECIMAL(18, 2))
    total_portfolio_value_eur = Column(DECIMAL(18, 2))

    # Technical impact
    affected_tables = Column(JSONB)
    affected_modules = Column(JSONB)
    estimated_dev_hours = Column(Integer)
    estimated_test_hours = Column(Integer)

    # Timeline
    regulatory_deadline = Column(Date)
    org_implementation_deadline = Column(Date)
    urgency_level = Column(String(20))  # 'low', 'medium', 'high', 'critical'

    # Status tracking
    alert_status = Column(String(50), default='new')  # 'new', 'viewed', 'acknowledged', 'in_progress', 'complete'
    email_sent_at = Column(DateTime(timezone=True))
    dashboard_viewed_at = Column(DateTime(timezone=True))
    acknowledged_at = Column(DateTime(timezone=True))

    # Benchmarking
    peer_count_affected = Column(Integer)
    peer_response_avg_weeks = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('org_id', 'change_id'),
        Index('idx_alerts_org_status', 'org_id', 'alert_status'),
        Index('idx_alerts_urgency', 'org_id', 'urgency_level'),
        Index('idx_alerts_deadline', 'org_implementation_deadline'),
    )

    organization = relationship('Organization')
    change = relationship('RegulatoryChange')
    framework = relationship('RegulatoryFramework')


class DashboardNotification(Base):
    __tablename__ = 'dashboard_notifications'

    notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey('organizations.org_id', ondelete='CASCADE'), nullable=False)
    alert_id = Column(UUID(as_uuid=True), ForeignKey('regulatory_alerts.alert_id', ondelete='CASCADE'))

    title = Column(String(255), nullable=False)
    message = Column(Text)
    notification_type = Column(String(50))  # 'regulatory_change', 'deadline_warning', 'task_update'
    severity = Column(String(20))  # 'critical', 'high', 'medium', 'low'

    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True))

    action_url = Column(Text)
    action_data = Column(JSONB)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    __table_args__ = (
        Index('idx_notifications_org_unread', 'org_id', 'is_read'),
        Index('idx_notifications_type', 'notification_type'),
    )

    organization = relationship('Organization')
    alert = relationship('RegulatoryAlert')
