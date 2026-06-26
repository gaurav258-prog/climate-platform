-- Climate Intelligence Platform - Initial Schema
-- Created: 2026-06-26
-- Database: PostgreSQL 14+
-- Extensions: TimescaleDB (for time-series optimization)

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- USERS & ORGANIZATIONS (Multi-tenancy)
-- ============================================================================

CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  subscription_tier VARCHAR(50) NOT NULL CHECK (subscription_tier IN ('starter', 'professional', 'enterprise')),
  api_key VARCHAR(255) UNIQUE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(50) NOT NULL CHECK (role IN ('admin', 'manager', 'analyst', 'responder')),
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_users_org_id ON users(org_id);
CREATE INDEX idx_users_email ON users(email);

-- ============================================================================
-- GEOGRAPHIC DATA
-- ============================================================================

CREATE TABLE locations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name VARCHAR(255) NOT NULL,
  latitude DECIMAL(10, 8) NOT NULL,
  longitude DECIMAL(11, 8) NOT NULL,
  region VARCHAR(100),
  country_code VARCHAR(2),
  population INT,
  h3_cell_res8 VARCHAR(15),
  h3_cell_res7 VARCHAR(15),
  h3_cell_res6 VARCHAR(15),
  geom GEOMETRY(POINT, 4326),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_locations_h3_res8 ON locations(h3_cell_res8);
CREATE INDEX idx_locations_geom ON locations USING GIST(geom);

CREATE TABLE h3_grid_cells (
  h3_id VARCHAR(15) PRIMARY KEY,
  resolution INT NOT NULL,
  latitude DECIMAL(10, 8) NOT NULL,
  longitude DECIMAL(11, 8) NOT NULL,
  parent_h3_id VARCHAR(15),
  geom GEOMETRY(POLYGON, 4326)
);

CREATE INDEX idx_h3_parent ON h3_grid_cells(parent_h3_id);

-- ============================================================================
-- RAW OBSERVATIONS (Ingest Layer)
-- ============================================================================

CREATE TABLE seismic_events (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source VARCHAR(50) NOT NULL,
  event_id VARCHAR(100) NOT NULL UNIQUE,
  magnitude DECIMAL(4, 2) NOT NULL,
  mag_type VARCHAR(10),
  latitude DECIMAL(10, 8) NOT NULL,
  longitude DECIMAL(11, 8) NOT NULL,
  depth_km DECIMAL(10, 2),
  origin_time TIMESTAMP WITH TIME ZONE NOT NULL,
  region_name VARCHAR(255),
  review_status VARCHAR(50),
  raw_data JSONB,
  ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(source, event_id)
);

CREATE TABLE flood_observations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source VARCHAR(50) NOT NULL,
  location_id UUID REFERENCES locations(id),
  h3_cell_res8 VARCHAR(15),
  water_level_m DECIMAL(10, 3),
  water_extent_km2 DECIMAL(12, 3),
  flood_severity VARCHAR(50),
  latitude DECIMAL(10, 8),
  longitude DECIMAL(11, 8),
  observation_time TIMESTAMP WITH TIME ZONE NOT NULL,
  raw_data JSONB,
  ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE wildfire_observations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source VARCHAR(50) NOT NULL,
  fire_id VARCHAR(100),
  latitude DECIMAL(10, 8) NOT NULL,
  longitude DECIMAL(11, 8) NOT NULL,
  confidence DECIMAL(3, 2),
  thermal_anomaly_mw DECIMAL(12, 2),
  fire_radiative_power DECIMAL(12, 2),
  observation_time TIMESTAMP WITH TIME ZONE NOT NULL,
  raw_data JSONB,
  ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE heat_observations (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source VARCHAR(50) NOT NULL,
  location_id UUID REFERENCES locations(id),
  h3_cell_res8 VARCHAR(15),
  temperature_c DECIMAL(5, 2),
  apparent_temperature_c DECIMAL(5, 2),
  relative_humidity_pct DECIMAL(5, 2),
  heat_index DECIMAL(5, 2),
  uhi_delta_c DECIMAL(5, 2),
  observation_time TIMESTAMP WITH TIME ZONE NOT NULL,
  raw_data JSONB,
  ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create hypertables for time-series optimization
SELECT create_hypertable('seismic_events', 'origin_time', if_not_exists => TRUE);
SELECT create_hypertable('flood_observations', 'observation_time', if_not_exists => TRUE);
SELECT create_hypertable('wildfire_observations', 'observation_time', if_not_exists => TRUE);
SELECT create_hypertable('heat_observations', 'observation_time', if_not_exists => TRUE);

-- Indexes for time-series queries
CREATE INDEX idx_seismic_org_time ON seismic_events(org_id, origin_time DESC);
CREATE INDEX idx_flood_org_h3_time ON flood_observations(org_id, h3_cell_res8, observation_time DESC);
CREATE INDEX idx_wildfire_org_time ON wildfire_observations(org_id, observation_time DESC);
CREATE INDEX idx_heat_org_h3_time ON heat_observations(org_id, h3_cell_res8, observation_time DESC);

-- ============================================================================
-- PREDICTIONS & RISK SCORES
-- ============================================================================

CREATE TABLE seismic_risk_scores (
  h3_cell_res8 VARCHAR(15) NOT NULL,
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  risk_score DECIMAL(5, 2) NOT NULL,
  damage_probability DECIMAL(3, 2),
  aftershock_24h_pct DECIMAL(5, 2),
  aftershock_72h_pct DECIMAL(5, 2),
  aftershock_7d_pct DECIMAL(5, 2),
  model_version VARCHAR(50),
  csep_validation_r2 DECIMAL(4, 3),
  computed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  PRIMARY KEY (h3_cell_res8, org_id, computed_at)
);

CREATE TABLE flood_risk_scores (
  h3_cell_res8 VARCHAR(15) NOT NULL,
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  risk_score DECIMAL(5, 2) NOT NULL,
  flood_probability DECIMAL(3, 2),
  water_level_forecast_m DECIMAL(10, 3),
  return_period_years INT,
  model_version VARCHAR(50),
  computed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  PRIMARY KEY (h3_cell_res8, org_id, computed_at)
);

CREATE TABLE wildfire_risk_scores (
  h3_cell_res8 VARCHAR(15) NOT NULL,
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  risk_score DECIMAL(5, 2) NOT NULL,
  fire_probability DECIMAL(3, 2),
  fuel_moisture_pct DECIMAL(5, 2),
  fire_weather_index DECIMAL(6, 2),
  model_version VARCHAR(50),
  computed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  PRIMARY KEY (h3_cell_res8, org_id, computed_at)
);

CREATE TABLE heat_risk_scores (
  h3_cell_res8 VARCHAR(15) NOT NULL,
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  risk_score DECIMAL(5, 2) NOT NULL,
  heat_probability DECIMAL(3, 2),
  max_temperature_c DECIMAL(5, 2),
  health_risk_level VARCHAR(50),
  model_version VARCHAR(50),
  computed_at TIMESTAMP WITH TIME ZONE NOT NULL,
  PRIMARY KEY (h3_cell_res8, org_id, computed_at)
);

-- Convert to hypertables
SELECT create_hypertable('seismic_risk_scores', 'computed_at', if_not_exists => TRUE);
SELECT create_hypertable('flood_risk_scores', 'computed_at', if_not_exists => TRUE);
SELECT create_hypertable('wildfire_risk_scores', 'computed_at', if_not_exists => TRUE);
SELECT create_hypertable('heat_risk_scores', 'computed_at', if_not_exists => TRUE);

-- ============================================================================
-- PARAMETRIC INSURANCE CONTRACTS
-- ============================================================================

CREATE TABLE parametric_contracts (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  hazard_type VARCHAR(50) NOT NULL CHECK (hazard_type IN ('flood', 'wildfire', 'heat', 'seismic')),
  coverage_region VARCHAR(255),
  trigger_index_type VARCHAR(100),
  trigger_threshold DECIMAL(10, 2) NOT NULL,
  payout_max DECIMAL(15, 2) NOT NULL,
  premium DECIMAL(15, 2) NOT NULL,
  status VARCHAR(50) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'underwriting', 'active', 'paused', 'expired')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE contract_triggers (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  contract_id UUID NOT NULL REFERENCES parametric_contracts(id) ON DELETE CASCADE,
  trigger_time TIMESTAMP WITH TIME ZONE NOT NULL,
  index_value DECIMAL(10, 3) NOT NULL,
  threshold_exceeded BOOLEAN NOT NULL,
  payout_amount DECIMAL(15, 2),
  status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'paid', 'denied')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_contracts_org ON parametric_contracts(org_id);
CREATE INDEX idx_triggers_contract ON contract_triggers(contract_id, trigger_time DESC);

-- ============================================================================
-- OPERATIONS & INCIDENT MANAGEMENT
-- ============================================================================

CREATE TABLE incidents (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  hazard_type VARCHAR(50) NOT NULL,
  location_id UUID REFERENCES locations(id),
  latitude DECIMAL(10, 8),
  longitude DECIMAL(11, 8),
  severity VARCHAR(50) NOT NULL CHECK (severity IN ('low', 'moderate', 'high', 'critical')),
  status VARCHAR(50) NOT NULL DEFAULT 'active' CHECK (status IN ('detected', 'active', 'escalated', 'resolved', 'archived')),
  responders_deployed INT DEFAULT 0,
  affected_population INT,
  estimated_loss_usd DECIMAL(15, 2),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE incident_timeline (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  incident_id UUID NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  event_type VARCHAR(100),
  description TEXT,
  created_by UUID REFERENCES users(id),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_incidents_org_status ON incidents(org_id, status);
CREATE INDEX idx_incidents_time ON incidents(created_at DESC);
CREATE INDEX idx_timeline_incident ON incident_timeline(incident_id, created_at DESC);

-- ============================================================================
-- AUDIT & COMPLIANCE
-- ============================================================================

CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id UUID REFERENCES users(id),
  action VARCHAR(100) NOT NULL,
  resource_type VARCHAR(100),
  resource_id VARCHAR(255),
  changes JSONB,
  ip_address INET,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE csep_validation_results (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  model_type VARCHAR(50) NOT NULL,
  test_name VARCHAR(100) NOT NULL,
  result VARCHAR(50),
  p_value DECIMAL(5, 4),
  information_gain_nats DECIMAL(10, 3),
  notes TEXT,
  validated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_org_time ON audit_logs(org_id, created_at DESC);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_csep_model ON csep_validation_results(model_type, validated_at DESC);

-- ============================================================================
-- DATA PIPELINE STATUS
-- ============================================================================

CREATE TABLE data_source_status (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source_name VARCHAR(100) NOT NULL UNIQUE,
  hazard_type VARCHAR(50),
  last_successful_fetch TIMESTAMP WITH TIME ZONE,
  last_fetch_attempt TIMESTAMP WITH TIME ZONE,
  last_error_message TEXT,
  records_fetched_today INT DEFAULT 0,
  is_healthy BOOLEAN DEFAULT true,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_source_status_hazard ON data_source_status(hazard_type);

-- ============================================================================
-- MATERIALIZED VIEWS FOR PERFORMANCE
-- ============================================================================

CREATE MATERIALIZED VIEW latest_risk_scores_by_cell AS
SELECT DISTINCT ON (h3_cell_res8)
  h3_cell_res8,
  risk_score,
  computed_at
FROM seismic_risk_scores
ORDER BY h3_cell_res8, computed_at DESC;

-- ============================================================================
-- GRANTS (Security)
-- ============================================================================

-- Data analysts can only read, not write
GRANT SELECT ON ALL TABLES IN SCHEMA public TO GROUP analysts;

-- Responders have limited access
GRANT SELECT ON incidents, incident_timeline, locations TO GROUP responders;

COMMIT;
