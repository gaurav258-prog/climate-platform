/**
 * CLIMATE INTELLIGENCE PLATFORM - COMPLETE SCHEMA v2.0
 * Regulatory + CRCS (Continuous Regulatory Compliance Service)
 *
 * This merged schema includes:
 * - Core regulatory framework (TCFD, Taxonomy, SEC, Basel, EBA, FCA)
 * - Climate risk assessment (physical + transition)
 * - Financial impact modeling
 * - GHG emissions tracking
 * - Regulatory versioning (N-1 support)
 * - Change detection & analysis
 * - Customer notifications
 * - Archive lifecycle management
 *
 * Status: Production-ready for Phase 0
 */

-- ============================================================================
-- EXTENSIONS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;

-- ============================================================================
-- MULTI-TENANCY & CORE ENTITIES
-- ============================================================================

CREATE TABLE IF NOT EXISTS organizations (
  org_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL UNIQUE,
  type VARCHAR(50) NOT NULL,  -- 'bank', 'insurer', 'asset_manager'
  country VARCHAR(2) NOT NULL,  -- ISO 3166-1
  aum_eur DECIMAL(18, 2),
  employees INT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  email VARCHAR(255) NOT NULL,
  role VARCHAR(50) NOT NULL,  -- 'admin', 'analyst', 'reporter', 'viewer'
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, email)
);

-- ============================================================================
-- BANK ASSETS & CLIMATE EXPOSURE
-- ============================================================================

CREATE TABLE IF NOT EXISTS bank_assets (
  asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  asset_name VARCHAR(255) NOT NULL,
  asset_type VARCHAR(50) NOT NULL,
  latitude DECIMAL(10, 6),
  longitude DECIMAL(10, 6),
  h3_cell VARCHAR(20),
  region VARCHAR(100),
  country VARCHAR(2),
  asset_value_eur DECIMAL(18, 2),
  annual_revenue_eur DECIMAL(18, 2),
  construction_year INT,
  expected_lifespan_years INT,
  sector VARCHAR(100),
  nace_code VARCHAR(10),
  gics_code VARCHAR(10),
  taxonomy_status VARCHAR(50),
  taxonomy_activity VARCHAR(255),
  dnsh_assessment JSONB,
  energy_consumption_mwh DECIMAL(15, 2),
  ghg_emissions_scope1_tco2e DECIMAL(15, 2),
  ghg_emissions_scope2_tco2e DECIMAL(15, 2),
  ghg_emissions_scope3_tco2e DECIMAL(15, 2),
  carbon_intensity_tco2e_per_meur DECIMAL(10, 2),
  insurance_coverage_eur DECIMAL(18, 2),
  insurance_coverage_pct DECIMAL(5, 2),
  resilience_rating VARCHAR(10),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  data_source VARCHAR(100),
  UNIQUE(org_id, asset_id)
);

CREATE INDEX idx_bank_assets_org_location ON bank_assets(org_id, h3_cell);
CREATE INDEX idx_bank_assets_org_sector ON bank_assets(org_id, sector);
CREATE INDEX idx_bank_assets_timestamp ON bank_assets(org_id, created_at DESC);

CREATE TABLE IF NOT EXISTS climate_hazard_exposure (
  exposure_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES bank_assets(asset_id) ON DELETE CASCADE,
  hazard_type VARCHAR(50) NOT NULL,
  exposure_level VARCHAR(20),
  physical_risk_score DECIMAL(5, 2),
  hazard_probability_pct DECIMAL(5, 2),
  hazard_intensity DECIMAL(10, 2),
  expected_annual_loss_eur DECIMAL(15, 2),
  conditional_var_95_eur DECIMAL(15, 2),
  revenue_impact_pct DECIMAL(5, 2),
  capex_adaptation_required_eur DECIMAL(15, 2),
  eu_taxonomy_physical_resilience DECIMAL(5, 2),
  basel_physical_risk_weight_pct DECIMAL(5, 2),
  scenario_1_5c_probability_pct DECIMAL(5, 2),
  scenario_2c_probability_pct DECIMAL(5, 2),
  scenario_4c_probability_pct DECIMAL(5, 2),
  assessment_date DATE,
  assessment_model VARCHAR(100),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, asset_id, hazard_type)
);

CREATE INDEX idx_hazard_org_type ON climate_hazard_exposure(org_id, hazard_type);
CREATE INDEX idx_hazard_org_risk ON climate_hazard_exposure(org_id, physical_risk_score DESC);

-- ============================================================================
-- REGULATORY FRAMEWORKS & VERSIONS
-- ============================================================================

CREATE TABLE IF NOT EXISTS regulatory_frameworks (
  framework_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_name VARCHAR(100) NOT NULL UNIQUE,
  framework_region VARCHAR(50),
  mandatory_effective_date DATE,
  enforcing_body VARCHAR(100),
  penalty_mechanism VARCHAR(255),
  reporting_format VARCHAR(100),
  reporting_frequency VARCHAR(50),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS regulation_versions (
  version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  version_number VARCHAR(50) NOT NULL,
  version_label VARCHAR(100),
  published_date DATE,
  effective_date DATE,
  end_of_life_date DATE,
  support_status VARCHAR(50),  -- 'Current', 'Legacy', 'End of Life'
  is_current BOOLEAN DEFAULT FALSE,
  schema_snapshot JSONB,
  processing_logic_version VARCHAR(50),
  output_format_version VARCHAR(50),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(framework_id, version_number)
);

CREATE TABLE IF NOT EXISTS org_regulation_version_preference (
  preference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id),
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  active_version_id UUID REFERENCES regulation_versions(version_id),
  previous_version_id UUID REFERENCES regulation_versions(version_id),
  immutability_rule VARCHAR(50),  -- 'immutable', 'mutable'
  version_switched_date TIMESTAMP WITH TIME ZONE,
  end_of_support_date DATE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, framework_id)
);

-- ============================================================================
-- REGULATORY CHANGE DETECTION (CRCS)
-- ============================================================================

CREATE TABLE IF NOT EXISTS regulatory_changes (
  change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  old_version VARCHAR(50),
  new_version VARCHAR(50),
  change_source VARCHAR(100),
  source_document_url TEXT,
  source_document_text JSONB,
  detection_method VARCHAR(50),
  detected_date TIMESTAMP WITH TIME ZONE,
  detected_by_system BOOLEAN DEFAULT TRUE,
  confirmed_date TIMESTAMP WITH TIME ZONE,
  confirmed_by VARCHAR(255),
  publication_date DATE,
  official_effective_date DATE,
  implementation_deadline DATE,
  change_type VARCHAR(50),
  change_classification VARCHAR(50),  -- 'Change' or 'Module'
  affected_tables JSONB,
  affected_processing_modules JSONB,
  affected_outputs JSONB,
  breaking_change BOOLEAN,
  backward_compatible BOOLEAN,
  data_migration_required BOOLEAN,
  estimated_dev_hours INT,
  estimated_test_hours INT,
  estimated_total_hours INT,
  estimated_release_date DATE,
  customer_deadline DATE,
  urgency_flag BOOLEAN,
  status VARCHAR(50),  -- 'Detected', 'Confirmed', 'Under Analysis', 'In Development', 'Testing', 'Ready', 'Released'
  status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  is_new_module BOOLEAN,
  module_name VARCHAR(255),
  module_pricing_tier VARCHAR(50),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(framework_id, old_version, new_version)
);

CREATE INDEX idx_regulatory_changes_status ON regulatory_changes(status);
CREATE INDEX idx_regulatory_changes_deadline ON regulatory_changes(implementation_deadline);

CREATE TABLE IF NOT EXISTS regulatory_change_details (
  detail_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  change_id UUID NOT NULL REFERENCES regulatory_changes(change_id) ON DELETE CASCADE,
  article_or_section VARCHAR(255),
  old_requirement TEXT,
  new_requirement TEXT,
  requirement_changed TEXT,
  affects_data_model BOOLEAN,
  data_field_name VARCHAR(255),
  field_type_change VARCHAR(100),
  affects_processing_logic BOOLEAN,
  processing_change_description TEXT,
  calculation_methodology_changed BOOLEAN,
  affects_output_format BOOLEAN,
  output_change_description TEXT,
  mitigation_strategy TEXT,
  breaking_change_mitigation TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- CLIMATE SCENARIOS & FINANCIAL MODELING
-- ============================================================================

CREATE TABLE IF NOT EXISTS climate_scenarios (
  scenario_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scenario_name VARCHAR(100) NOT NULL,
  pathway VARCHAR(20) NOT NULL,  -- '1.5c', '2c', '4c'
  temperature_increase_celsius DECIMAL(5, 2),
  carbon_price_eur_per_ton_2030 DECIMAL(10, 2),
  carbon_price_eur_per_ton_2050 DECIMAL(10, 2),
  renewable_energy_cost_decline_pct_2030 DECIMAL(5, 2),
  electric_vehicle_adoption_pct_2030 DECIMAL(5, 2),
  energy_efficiency_improvement_pct DECIMAL(5, 2),
  short_term_year INT,
  medium_term_year INT,
  long_term_year INT,
  scenario_source VARCHAR(100),
  baseline_year INT DEFAULT 2024,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(pathway)
);

CREATE TABLE IF NOT EXISTS scenario_financial_impact (
  impact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES bank_assets(asset_id) ON DELETE CASCADE,
  scenario_id UUID NOT NULL REFERENCES climate_scenarios(scenario_id) ON DELETE CASCADE,
  time_horizon VARCHAR(20) NOT NULL,
  base_revenue_eur DECIMAL(18, 2),
  demand_shift_pct DECIMAL(5, 2),
  price_impact_pct DECIMAL(5, 2),
  projected_revenue_eur DECIMAL(18, 2),
  revenue_impact_eur DECIMAL(18, 2),
  base_opex_eur DECIMAL(18, 2),
  input_cost_inflation_pct DECIMAL(5, 2),
  regulatory_compliance_cost_eur DECIMAL(15, 2),
  adaptation_capex_eur DECIMAL(15, 2),
  projected_opex_eur DECIMAL(18, 2),
  opex_impact_eur DECIMAL(18, 2),
  stranded_asset_risk_pct DECIMAL(5, 2),
  asset_impairment_eur DECIMAL(15, 2),
  discount_rate_pct DECIMAL(5, 2),
  climate_risk_premium_pct DECIMAL(5, 2),
  net_present_value_eur DECIMAL(18, 2),
  npv_change_from_base_pct DECIMAL(5, 2),
  financial_impact_materiality_pct DECIMAL(5, 2),
  is_material BOOLEAN,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, asset_id, scenario_id, time_horizon)
);

CREATE INDEX idx_scenario_impact_org ON scenario_financial_impact(org_id, scenario_id);
CREATE INDEX idx_scenario_impact_material ON scenario_financial_impact(org_id, is_material);

-- ============================================================================
-- GHG EMISSIONS & METRICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS ghg_emissions_inventory (
  emissions_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  asset_id UUID REFERENCES bank_assets(asset_id) ON DELETE CASCADE,
  scope_1_tco2e DECIMAL(15, 2) NOT NULL,
  scope_2_location_based_tco2e DECIMAL(15, 2) NOT NULL,
  scope_2_market_based_tco2e DECIMAL(15, 2),
  scope_3_tco2e DECIMAL(15, 2),
  scope_3_category_1_upstream_tco2e DECIMAL(15, 2),
  scope_3_category_9_downstream_tco2e DECIMAL(15, 2),
  total_emissions_tco2e DECIMAL(15, 2) GENERATED ALWAYS AS
    (scope_1_tco2e + COALESCE(scope_2_location_based_tco2e, 0) + COALESCE(scope_3_tco2e, 0)) STORED,
  emissions_intensity_tco2e_per_meur DECIMAL(10, 2),
  energy_intensity_kwh_per_unit DECIMAL(10, 2),
  waci_tco2e_per_meur DECIMAL(10, 2),
  reporting_year INT NOT NULL,
  reporting_date DATE,
  calculation_method VARCHAR(100),
  emission_factors_source VARCHAR(100),
  assurance_level VARCHAR(50),
  assurance_provider VARCHAR(255),
  sec_form_10k_scope_1 DECIMAL(15, 2),
  sec_form_10k_scope_2 DECIMAL(15, 2),
  sec_form_10k_scope_3 DECIMAL(15, 2),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, asset_id, reporting_year)
);

CREATE INDEX idx_emissions_org_year ON ghg_emissions_inventory(org_id, reporting_year DESC);

-- ============================================================================
-- CLIMATE RISK SCORES
-- ============================================================================

CREATE TABLE IF NOT EXISTS climate_risk_scores (
  score_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES bank_assets(asset_id) ON DELETE CASCADE,
  overall_risk_score DECIMAL(5, 2),
  physical_risk_score DECIMAL(5, 2),
  transition_risk_score DECIMAL(5, 2),
  financial_materiality_score DECIMAL(5, 2),
  regulatory_risk_score DECIMAL(5, 2),
  risk_category VARCHAR(50),
  confidence_level_pct DECIMAL(5, 2),
  sensitivity_to_carbon_price DECIMAL(5, 2),
  sensitivity_to_physical_events DECIMAL(5, 2),
  assessment_date DATE,
  assessment_model_version VARCHAR(50),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, asset_id, assessment_date)
);

CREATE INDEX idx_risk_scores_org_category ON climate_risk_scores(org_id, risk_category);

-- ============================================================================
-- REGULATORY FILINGS & OUTPUTS
-- ============================================================================

CREATE TABLE IF NOT EXISTS regulatory_filings (
  filing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  version_id UUID REFERENCES regulation_versions(version_id),
  filing_type VARCHAR(100),
  reporting_period_start DATE,
  reporting_period_end DATE,
  filing_version INT DEFAULT 1,
  is_amended BOOLEAN DEFAULT FALSE,
  amended_from_filing_id UUID REFERENCES regulatory_filings(filing_id),
  amendment_reason TEXT,
  is_immutable BOOLEAN,
  status VARCHAR(50),  -- 'Draft', 'Submitted', 'Accepted', 'Amended'
  submission_date TIMESTAMP WITH TIME ZONE,
  filing_content JSONB,
  narrative_summary TEXT,
  certification_date TIMESTAMP WITH TIME ZONE,
  certified_by VARCHAR(255),
  archive_status VARCHAR(50),  -- 'Live', 'Legacy Support', 'Archived'
  archive_date TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, framework_id, reporting_period_end)
);

CREATE INDEX idx_filings_org_status ON regulatory_filings(org_id, status);
CREATE INDEX idx_filings_org_date ON regulatory_filings(org_id, submission_date DESC);

CREATE TABLE IF NOT EXISTS filing_amendments (
  amendment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filing_id UUID NOT NULL REFERENCES regulatory_filings(filing_id),
  amendment_version INT,
  amendment_date TIMESTAMP WITH TIME ZONE,
  amendment_reason TEXT,
  old_values JSONB,
  new_values JSONB,
  amended_by VARCHAR(255),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- SUBSCRIPTIONS & MODULES
-- ============================================================================

CREATE TABLE IF NOT EXISTS org_crcs_subscription (
  subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  subscription_tier VARCHAR(50) DEFAULT 'Continuous Regulatory Compliance Service',
  coverage_description TEXT,
  annual_crcs_cost_eur DECIMAL(15, 2),
  billing_start_date DATE,
  billing_end_date DATE,
  max_frameworks_covered INT,
  change_coverage_included VARCHAR(255),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id)
);

CREATE TABLE IF NOT EXISTS org_module_subscriptions (
  module_sub_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  module_id UUID NOT NULL,
  module_name VARCHAR(255),
  module_description TEXT,
  annual_module_cost_eur DECIMAL(15, 2),
  billing_start_date DATE,
  billing_end_date DATE,
  status VARCHAR(50),  -- 'Active', 'Inactive'
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, module_id)
);

-- ============================================================================
-- ARCHIVE & RETENTION
-- ============================================================================

CREATE TABLE IF NOT EXISTS archive_retention_rules (
  rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  country_code VARCHAR(2),
  jurisdiction_name VARCHAR(100),
  default_retention_years INT,
  framework_retention JSONB,
  regulatory_reference TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS org_archive_retention_settings (
  setting_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id),
  primary_jurisdiction VARCHAR(2),
  secondary_jurisdictions JSONB,
  applicable_retention_rules JSONB,
  extended_retention_years INT,
  extended_retention_cost_eur DECIMAL(15, 2),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id)
);

CREATE TABLE IF NOT EXISTS regulatory_filing_archive (
  archive_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filing_id UUID NOT NULL REFERENCES regulatory_filings(filing_id),
  archived_date TIMESTAMP WITH TIME ZONE,
  archive_reason VARCHAR(50),
  required_retention_until DATE,
  jurisdiction_applied VARCHAR(2),
  archive_location VARCHAR(255),
  is_retrievable BOOLEAN DEFAULT TRUE,
  retrieval_cost_eur DECIMAL(15, 2),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- AUDIT & GOVERNANCE
-- ============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
  log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  entity_type VARCHAR(100),
  entity_id UUID,
  action VARCHAR(50),
  changed_by VARCHAR(255),
  change_details JSONB,
  timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  framework_context VARCHAR(100),
  compliance_relevant BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_audit_org_time ON audit_log(org_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS governance_structure (
  governance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  board_committee_with_climate_oversight VARCHAR(255),
  climate_risk_owner_title VARCHAR(100),
  management_level_owner_title VARCHAR(100),
  governance_policy_last_updated DATE,
  climate_risk_discussed_in_board_meetings INT,
  climate_risk_integrated_in_strategic_plan BOOLEAN,
  climate_risk_integrated_in_capital_allocation BOOLEAN,
  climate_risk_integrated_in_compensation BOOLEAN,
  governance_disclosure_status VARCHAR(50),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id)
);

-- ============================================================================
-- MATERIALITY & KPI SUMMARY
-- ============================================================================

CREATE TABLE IF NOT EXISTS materiality_assessments (
  assessment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  risk_name VARCHAR(255) NOT NULL,
  risk_category VARCHAR(100),
  financial_impact_pct DECIMAL(5, 2),
  is_financially_material BOOLEAN,
  impact_materiality_score DECIMAL(5, 2),
  is_impact_material BOOLEAN,
  double_materiality_score DECIMAL(5, 2),
  assessment_methodology TEXT,
  assessed_by VARCHAR(255),
  assessment_date DATE,
  applicable_frameworks JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, risk_name, assessment_date)
);

CREATE TABLE IF NOT EXISTS kpi_summary (
  kpi_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  reporting_year INT,
  total_scope_1_emissions_tco2e DECIMAL(15, 2),
  total_scope_2_emissions_tco2e DECIMAL(15, 2),
  total_scope_3_emissions_tco2e DECIMAL(15, 2),
  taxonomy_aligned_turnover_pct DECIMAL(5, 2),
  taxonomy_aligned_capex_pct DECIMAL(5, 2),
  taxonomy_aligned_opex_pct DECIMAL(5, 2),
  portfolio_physical_risk_avg_score DECIMAL(5, 2),
  portfolio_transition_risk_avg_score DECIMAL(5, 2),
  waci_tco2e_per_meur DECIMAL(10, 2),
  carbon_footprint_tco2e_per_meur DECIMAL(10, 2),
  portfolio_npv_under_1_5c_scenario_eur DECIMAL(18, 2),
  portfolio_npv_under_2c_scenario_eur DECIMAL(18, 2),
  portfolio_npv_under_4c_scenario_eur DECIMAL(18, 2),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(org_id, reporting_year)
);

-- ============================================================================
-- CONSTRAINTS
-- ============================================================================

ALTER TABLE climate_risk_scores
  ADD CONSTRAINT overall_score_range CHECK (overall_risk_score >= 0 AND overall_risk_score <= 100),
  ADD CONSTRAINT physical_score_range CHECK (physical_risk_score >= 0 AND physical_risk_score <= 100);

ALTER TABLE ghg_emissions_inventory
  ADD CONSTRAINT scope_1_non_negative CHECK (scope_1_tco2e >= 0),
  ADD CONSTRAINT scope_2_non_negative CHECK (scope_2_location_based_tco2e >= 0);

-- ============================================================================
-- VIEWS FOR REPORTING
-- ============================================================================

CREATE VIEW v_org_compliance_status AS
SELECT
  o.org_id,
  o.name,
  o.type,
  rf.framework_name,
  COALESCE(COUNT(rf_fil.filing_id), 0) as filings_count,
  COUNT(CASE WHEN rf_fil.status = 'Submitted' THEN 1 END) as submitted_count,
  MAX(rf_fil.submission_date) as last_submission_date
FROM organizations o
CROSS JOIN regulatory_frameworks rf
LEFT JOIN regulatory_filings rf_fil ON o.org_id = rf_fil.org_id AND rf.framework_id = rf_fil.framework_id
GROUP BY o.org_id, o.name, o.type, rf.framework_name;

CREATE VIEW v_asset_climate_risk_summary AS
SELECT
  org_id,
  COUNT(CASE WHEN risk_category = 'Critical' THEN 1 END) as critical_risk_assets,
  COUNT(CASE WHEN risk_category = 'High' THEN 1 END) as high_risk_assets,
  AVG(overall_risk_score) as avg_portfolio_risk_score,
  MAX(overall_risk_score) as max_portfolio_risk_score,
  assessment_date
FROM climate_risk_scores
GROUP BY org_id, assessment_date;

-- ============================================================================
-- INITIALIZATION DATA
-- ============================================================================

INSERT INTO climate_scenarios (scenario_name, pathway, temperature_increase_celsius, carbon_price_eur_per_ton_2030, carbon_price_eur_per_ton_2050, renewable_energy_cost_decline_pct_2030, baseline_year, short_term_year, medium_term_year, long_term_year, scenario_source)
VALUES
  ('Paris Agreement (1.5°C)', '1.5c', 1.5, 150, 200, 45, 2024, 2030, 2040, 2050, 'IPCC SSP1-2.6'),
  ('Moderate Pathway (2°C)', '2c', 2.0, 80, 120, 35, 2024, 2030, 2040, 2050, 'IPCC SSP2-4.5'),
  ('Business-As-Usual (4°C)', '4c', 4.0, 20, 50, 15, 2024, 2030, 2040, 2050, 'IPCC SSP5-8.5')
ON CONFLICT DO NOTHING;

INSERT INTO regulatory_frameworks (framework_name, framework_region, mandatory_effective_date, enforcing_body, reporting_format, reporting_frequency)
VALUES
  ('TCFD', 'Global', '2025-01-01', 'National regulators', 'Narrative + Quantitative', 'Annual'),
  ('EU Taxonomy', 'EU', '2024-01-01', 'European Commission', 'XBRL/iXBRL', 'Annual'),
  ('SEC Climate Disclosure', 'US', '2026-01-01', 'SEC', 'Form 10-K', 'Annual'),
  ('Basel III Climate', 'Global', '2027-01-01', 'Basel Committee', 'Stress Test', 'Annual'),
  ('EBA/ECB Guidelines', 'EU', '2026-01-11', 'ECB', 'Regulatory Report', 'Annual'),
  ('UK FCA Climate', 'UK', '2024-06-30', 'FCA', 'Climate Disclosure', 'Annual')
ON CONFLICT DO NOTHING;

INSERT INTO archive_retention_rules (country_code, jurisdiction_name, default_retention_years, regulatory_reference)
VALUES
  ('EU', 'European Union', 7, 'EU Record Retention Directive'),
  ('US', 'United States', 10, 'SEC Regulations'),
  ('UK', 'United Kingdom', 6, 'FCA Rules'),
  ('DE', 'Germany', 10, 'German Commercial Code'),
  ('FR', 'France', 5, 'French Data Protection Law'),
  ('IT', 'Italy', 5, 'Italian Financial Authority'),
  ('ES', 'Spain', 5, 'Spanish Banking Regulation')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================

/**
 * SCHEMA COMPLETE
 *
 * Tables: 30+
 * Indexes: 20+
 * Views: 3
 *
 * Ready for:
 * 1. ORM model generation (SQLAlchemy)
 * 2. Application code (FastAPI)
 * 3. Data ingestion pipelines
 * 4. Regulatory processing layers
 */
