-- Frozen DDL of the 22 tables revision d9e3f4a5b6c7 creates — exactly what its former ORM create_all produced,
-- read from a scratch database built to that revision (pg_dump -s). A migration never reads live code (E25).
CREATE TABLE public.bank_assets (
    asset_id uuid NOT NULL,
    org_id uuid NOT NULL,
    asset_name character varying(255) NOT NULL,
    asset_type character varying(50) NOT NULL,
    latitude numeric(10,6),
    longitude numeric(10,6),
    h3_cell character varying(20),
    region character varying(100),
    country character varying(2),
    asset_value_eur numeric(18,2),
    annual_revenue_eur numeric(18,2),
    construction_year integer,
    expected_lifespan_years integer,
    sector character varying(100),
    nace_code character varying(10),
    gics_code character varying(10),
    taxonomy_status character varying(50),
    taxonomy_activity character varying(255),
    dnsh_assessment jsonb,
    energy_consumption_mwh numeric(15,2),
    ghg_emissions_scope1_tco2e numeric(15,2),
    ghg_emissions_scope2_tco2e numeric(15,2),
    ghg_emissions_scope3_tco2e numeric(15,2),
    carbon_intensity_tco2e_per_meur numeric(10,2),
    insurance_coverage_eur numeric(18,2),
    insurance_coverage_pct numeric(5,2),
    resilience_rating character varying(10),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    data_source character varying(100)
);
CREATE TABLE public.climate_hazard_exposure (
    exposure_id uuid NOT NULL,
    org_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    hazard_type character varying(50) NOT NULL,
    exposure_level character varying(20),
    physical_risk_score numeric(5,2),
    hazard_probability_pct numeric(5,2),
    hazard_intensity numeric(10,2),
    expected_annual_loss_eur numeric(15,2),
    conditional_var_95_eur numeric(15,2),
    revenue_impact_pct numeric(5,2),
    capex_adaptation_required_eur numeric(15,2),
    eu_taxonomy_physical_resilience numeric(5,2),
    basel_physical_risk_weight_pct numeric(5,2),
    scenario_1_5c_probability_pct numeric(5,2),
    scenario_2c_probability_pct numeric(5,2),
    scenario_4c_probability_pct numeric(5,2),
    assessment_date date,
    assessment_model character varying(100),
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.climate_risk_scores (
    score_id uuid NOT NULL,
    org_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    overall_risk_score numeric(5,2),
    physical_risk_score numeric(5,2),
    transition_risk_score numeric(5,2),
    financial_materiality_score numeric(5,2),
    regulatory_risk_score numeric(5,2),
    risk_category character varying(50),
    confidence_level_pct numeric(5,2),
    sensitivity_to_carbon_price numeric(5,2),
    sensitivity_to_physical_events numeric(5,2),
    assessment_date date,
    assessment_model_version character varying(50),
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.climate_scenarios (
    scenario_id uuid NOT NULL,
    scenario_name character varying(100) NOT NULL,
    pathway character varying(20) NOT NULL,
    temperature_increase_celsius numeric(5,2),
    carbon_price_eur_per_ton_2030 numeric(10,2),
    carbon_price_eur_per_ton_2050 numeric(10,2),
    renewable_energy_cost_decline_pct_2030 numeric(5,2),
    electric_vehicle_adoption_pct_2030 numeric(5,2),
    energy_efficiency_improvement_pct numeric(5,2),
    short_term_year integer,
    medium_term_year integer,
    long_term_year integer,
    scenario_source character varying(100),
    baseline_year integer,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.dashboard_notifications (
    notification_id uuid NOT NULL,
    org_id uuid NOT NULL,
    alert_id uuid,
    title character varying(255) NOT NULL,
    message text,
    notification_type character varying(50),
    severity character varying(20),
    is_read boolean,
    read_at timestamp with time zone,
    action_url text,
    action_data jsonb,
    created_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone
);
CREATE TABLE public.filing_amendments (
    amendment_id uuid NOT NULL,
    filing_id uuid NOT NULL,
    amendment_version integer,
    amendment_date timestamp with time zone,
    amendment_reason text,
    old_values jsonb,
    new_values jsonb,
    amended_by character varying(255),
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.ghg_emissions_inventory (
    emissions_id uuid NOT NULL,
    org_id uuid NOT NULL,
    asset_id uuid,
    scope_1_tco2e numeric(15,2) NOT NULL,
    scope_2_location_based_tco2e numeric(15,2) NOT NULL,
    scope_2_market_based_tco2e numeric(15,2),
    scope_3_tco2e numeric(15,2),
    scope_3_category_1_upstream_tco2e numeric(15,2),
    scope_3_category_9_downstream_tco2e numeric(15,2),
    emissions_intensity_tco2e_per_meur numeric(10,2),
    energy_intensity_kwh_per_unit numeric(10,2),
    waci_tco2e_per_meur numeric(10,2),
    reporting_year integer NOT NULL,
    reporting_date date,
    calculation_method character varying(100),
    emission_factors_source character varying(100),
    assurance_level character varying(50),
    assurance_provider character varying(255),
    sec_form_10k_scope_1 numeric(15,2),
    sec_form_10k_scope_2 numeric(15,2),
    sec_form_10k_scope_3 numeric(15,2),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.governance_structure (
    governance_id uuid NOT NULL,
    org_id uuid NOT NULL,
    board_committee_with_climate_oversight character varying(255),
    climate_risk_owner_title character varying(100),
    management_level_owner_title character varying(100),
    governance_policy_last_updated date,
    climate_risk_discussed_in_board_meetings integer,
    climate_risk_integrated_in_strategic_plan boolean,
    climate_risk_integrated_in_capital_allocation boolean,
    climate_risk_integrated_in_compensation boolean,
    governance_disclosure_status character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.kpi_summary (
    kpi_id uuid NOT NULL,
    org_id uuid NOT NULL,
    reporting_year integer,
    total_scope_1_emissions_tco2e numeric(15,2),
    total_scope_2_emissions_tco2e numeric(15,2),
    total_scope_3_emissions_tco2e numeric(15,2),
    taxonomy_aligned_turnover_pct numeric(5,2),
    taxonomy_aligned_capex_pct numeric(5,2),
    taxonomy_aligned_opex_pct numeric(5,2),
    portfolio_physical_risk_avg_score numeric(5,2),
    portfolio_transition_risk_avg_score numeric(5,2),
    waci_tco2e_per_meur numeric(10,2),
    carbon_footprint_tco2e_per_meur numeric(10,2),
    portfolio_npv_under_1_5c_scenario_eur numeric(18,2),
    portfolio_npv_under_2c_scenario_eur numeric(18,2),
    portfolio_npv_under_4c_scenario_eur numeric(18,2),
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.org_crcs_subscription (
    subscription_id uuid NOT NULL,
    org_id uuid NOT NULL,
    subscription_tier character varying(50),
    coverage_description text,
    annual_crcs_cost_eur numeric(15,2),
    billing_start_date date,
    billing_end_date date,
    max_frameworks_covered integer,
    change_coverage_included character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.org_module_subscriptions (
    module_sub_id uuid NOT NULL,
    org_id uuid NOT NULL,
    module_id uuid NOT NULL,
    module_name character varying(255),
    module_description text,
    annual_module_cost_eur numeric(15,2),
    billing_start_date date,
    billing_end_date date,
    status character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.org_regulation_version_preference (
    preference_id uuid NOT NULL,
    org_id uuid NOT NULL,
    framework_id uuid NOT NULL,
    active_version_id uuid,
    previous_version_id uuid,
    immutability_rule character varying(50),
    version_switched_date timestamp with time zone,
    end_of_support_date date,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.organizations (
    org_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    type character varying(50) NOT NULL,
    country character varying(2) NOT NULL,
    aum_eur numeric(18,2),
    employees integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.regulation_versions (
    version_id uuid NOT NULL,
    framework_id uuid NOT NULL,
    version_number character varying(50) NOT NULL,
    version_label character varying(100),
    published_date date,
    effective_date date,
    end_of_life_date date,
    support_status character varying(50),
    is_current boolean,
    schema_snapshot jsonb,
    processing_logic_version character varying(50),
    output_format_version character varying(50),
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.regulatory_alerts (
    alert_id uuid NOT NULL,
    org_id uuid NOT NULL,
    change_id uuid,
    framework_id uuid NOT NULL,
    affected_asset_count integer,
    total_assets integer,
    portfolio_value_affected_eur numeric(18,2),
    total_portfolio_value_eur numeric(18,2),
    affected_tables jsonb,
    affected_modules jsonb,
    estimated_dev_hours integer,
    estimated_test_hours integer,
    regulatory_deadline date,
    org_implementation_deadline date,
    urgency_level character varying(20),
    alert_status character varying(50),
    email_sent_at timestamp with time zone,
    dashboard_viewed_at timestamp with time zone,
    acknowledged_at timestamp with time zone,
    peer_count_affected integer,
    peer_response_avg_weeks integer,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.regulatory_audit_log (
    log_id uuid NOT NULL,
    org_id uuid NOT NULL,
    entity_type character varying(100),
    entity_id uuid,
    action character varying(50),
    changed_by character varying(255),
    change_details jsonb,
    "timestamp" timestamp with time zone DEFAULT now(),
    framework_context character varying(100),
    compliance_relevant boolean
);
CREATE TABLE public.regulatory_change_details (
    detail_id uuid NOT NULL,
    change_id uuid NOT NULL,
    article_or_section character varying(255),
    old_requirement text,
    new_requirement text,
    requirement_changed text,
    affects_data_model boolean,
    data_field_name character varying(255),
    field_type_change character varying(100),
    affects_processing_logic boolean,
    processing_change_description text,
    calculation_methodology_changed boolean,
    affects_output_format boolean,
    output_change_description text,
    mitigation_strategy text,
    breaking_change_mitigation text,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.regulatory_changes (
    change_id uuid NOT NULL,
    framework_id uuid NOT NULL,
    old_version character varying(50),
    new_version character varying(50),
    change_source character varying(100),
    source_document_url text,
    source_document_text jsonb,
    detection_method character varying(50),
    detected_date timestamp with time zone,
    detected_by_system boolean,
    confirmed_date timestamp with time zone,
    confirmed_by character varying(255),
    publication_date date,
    official_effective_date date,
    implementation_deadline date,
    change_type character varying(50),
    change_classification character varying(50),
    affected_tables jsonb,
    affected_processing_modules jsonb,
    affected_outputs jsonb,
    breaking_change boolean,
    backward_compatible boolean,
    data_migration_required boolean,
    estimated_dev_hours integer,
    estimated_test_hours integer,
    estimated_total_hours integer,
    estimated_release_date date,
    customer_deadline date,
    urgency_flag boolean,
    status character varying(50),
    status_updated_at timestamp with time zone DEFAULT now(),
    is_new_module boolean,
    module_name character varying(255),
    module_pricing_tier character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.regulatory_filings (
    filing_id uuid NOT NULL,
    org_id uuid NOT NULL,
    framework_id uuid NOT NULL,
    version_id uuid,
    filing_type character varying(100),
    reporting_period_start date,
    reporting_period_end date,
    filing_version integer,
    is_amended boolean,
    amended_from_filing_id uuid,
    amendment_reason text,
    is_immutable boolean,
    status character varying(50),
    submission_date timestamp with time zone,
    filing_content jsonb,
    narrative_summary text,
    certification_date timestamp with time zone,
    certified_by character varying(255),
    archive_status character varying(50),
    archive_date timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.regulatory_frameworks (
    framework_id uuid NOT NULL,
    framework_name character varying(100) NOT NULL,
    framework_region character varying(50),
    mandatory_effective_date date,
    enforcing_body character varying(100),
    penalty_mechanism character varying(255),
    reporting_format character varying(100),
    reporting_frequency character varying(50),
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.scenario_financial_impact (
    impact_id uuid NOT NULL,
    org_id uuid NOT NULL,
    asset_id uuid NOT NULL,
    scenario_id uuid NOT NULL,
    time_horizon character varying(20) NOT NULL,
    base_revenue_eur numeric(18,2),
    demand_shift_pct numeric(5,2),
    price_impact_pct numeric(5,2),
    projected_revenue_eur numeric(18,2),
    revenue_impact_eur numeric(18,2),
    base_opex_eur numeric(18,2),
    input_cost_inflation_pct numeric(5,2),
    regulatory_compliance_cost_eur numeric(15,2),
    adaptation_capex_eur numeric(15,2),
    projected_opex_eur numeric(18,2),
    opex_impact_eur numeric(18,2),
    stranded_asset_risk_pct numeric(5,2),
    asset_impairment_eur numeric(15,2),
    discount_rate_pct numeric(5,2),
    climate_risk_premium_pct numeric(5,2),
    net_present_value_eur numeric(18,2),
    npv_change_from_base_pct numeric(5,2),
    financial_impact_materiality_pct numeric(5,2),
    is_material boolean,
    created_at timestamp with time zone DEFAULT now()
);
CREATE TABLE public.users (
    user_id uuid NOT NULL,
    org_id uuid NOT NULL,
    email character varying(255) NOT NULL,
    role character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);
ALTER TABLE ONLY public.bank_assets
    ADD CONSTRAINT bank_assets_org_id_asset_id_key UNIQUE (org_id, asset_id);
ALTER TABLE ONLY public.bank_assets
    ADD CONSTRAINT bank_assets_pkey PRIMARY KEY (asset_id);
ALTER TABLE ONLY public.climate_hazard_exposure
    ADD CONSTRAINT climate_hazard_exposure_org_id_asset_id_hazard_type_key UNIQUE (org_id, asset_id, hazard_type);
ALTER TABLE ONLY public.climate_hazard_exposure
    ADD CONSTRAINT climate_hazard_exposure_pkey PRIMARY KEY (exposure_id);
ALTER TABLE ONLY public.climate_risk_scores
    ADD CONSTRAINT climate_risk_scores_org_id_asset_id_assessment_date_key UNIQUE (org_id, asset_id, assessment_date);
ALTER TABLE ONLY public.climate_risk_scores
    ADD CONSTRAINT climate_risk_scores_pkey PRIMARY KEY (score_id);
ALTER TABLE ONLY public.climate_scenarios
    ADD CONSTRAINT climate_scenarios_pathway_key UNIQUE (pathway);
ALTER TABLE ONLY public.climate_scenarios
    ADD CONSTRAINT climate_scenarios_pkey PRIMARY KEY (scenario_id);
ALTER TABLE ONLY public.dashboard_notifications
    ADD CONSTRAINT dashboard_notifications_pkey PRIMARY KEY (notification_id);
ALTER TABLE ONLY public.filing_amendments
    ADD CONSTRAINT filing_amendments_pkey PRIMARY KEY (amendment_id);
ALTER TABLE ONLY public.ghg_emissions_inventory
    ADD CONSTRAINT ghg_emissions_inventory_org_id_asset_id_reporting_year_key UNIQUE (org_id, asset_id, reporting_year);
ALTER TABLE ONLY public.ghg_emissions_inventory
    ADD CONSTRAINT ghg_emissions_inventory_pkey PRIMARY KEY (emissions_id);
ALTER TABLE ONLY public.governance_structure
    ADD CONSTRAINT governance_structure_org_id_key UNIQUE (org_id);
ALTER TABLE ONLY public.governance_structure
    ADD CONSTRAINT governance_structure_pkey PRIMARY KEY (governance_id);
ALTER TABLE ONLY public.kpi_summary
    ADD CONSTRAINT kpi_summary_org_id_reporting_year_key UNIQUE (org_id, reporting_year);
ALTER TABLE ONLY public.kpi_summary
    ADD CONSTRAINT kpi_summary_pkey PRIMARY KEY (kpi_id);
ALTER TABLE ONLY public.org_crcs_subscription
    ADD CONSTRAINT org_crcs_subscription_org_id_key UNIQUE (org_id);
ALTER TABLE ONLY public.org_crcs_subscription
    ADD CONSTRAINT org_crcs_subscription_pkey PRIMARY KEY (subscription_id);
ALTER TABLE ONLY public.org_module_subscriptions
    ADD CONSTRAINT org_module_subscriptions_org_id_module_id_key UNIQUE (org_id, module_id);
ALTER TABLE ONLY public.org_module_subscriptions
    ADD CONSTRAINT org_module_subscriptions_pkey PRIMARY KEY (module_sub_id);
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_org_id_framework_id_key UNIQUE (org_id, framework_id);
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_pkey PRIMARY KEY (preference_id);
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_name_key UNIQUE (name);
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (org_id);
ALTER TABLE ONLY public.regulation_versions
    ADD CONSTRAINT regulation_versions_framework_id_version_number_key UNIQUE (framework_id, version_number);
ALTER TABLE ONLY public.regulation_versions
    ADD CONSTRAINT regulation_versions_pkey PRIMARY KEY (version_id);
ALTER TABLE ONLY public.regulatory_alerts
    ADD CONSTRAINT regulatory_alerts_org_id_change_id_key UNIQUE (org_id, change_id);
ALTER TABLE ONLY public.regulatory_alerts
    ADD CONSTRAINT regulatory_alerts_pkey PRIMARY KEY (alert_id);
ALTER TABLE ONLY public.regulatory_audit_log
    ADD CONSTRAINT regulatory_audit_log_pkey PRIMARY KEY (log_id);
ALTER TABLE ONLY public.regulatory_change_details
    ADD CONSTRAINT regulatory_change_details_pkey PRIMARY KEY (detail_id);
ALTER TABLE ONLY public.regulatory_changes
    ADD CONSTRAINT regulatory_changes_framework_id_old_version_new_version_key UNIQUE (framework_id, old_version, new_version);
ALTER TABLE ONLY public.regulatory_changes
    ADD CONSTRAINT regulatory_changes_pkey PRIMARY KEY (change_id);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_org_id_framework_id_reporting_period_end_key UNIQUE (org_id, framework_id, reporting_period_end);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_pkey PRIMARY KEY (filing_id);
ALTER TABLE ONLY public.regulatory_frameworks
    ADD CONSTRAINT regulatory_frameworks_framework_name_key UNIQUE (framework_name);
ALTER TABLE ONLY public.regulatory_frameworks
    ADD CONSTRAINT regulatory_frameworks_pkey PRIMARY KEY (framework_id);
ALTER TABLE ONLY public.scenario_financial_impact
    ADD CONSTRAINT scenario_financial_impact_org_id_asset_id_scenario_id_time__key UNIQUE (org_id, asset_id, scenario_id, time_horizon);
ALTER TABLE ONLY public.scenario_financial_impact
    ADD CONSTRAINT scenario_financial_impact_pkey PRIMARY KEY (impact_id);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_org_id_email_key UNIQUE (org_id, email);
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);
CREATE INDEX idx_alerts_deadline ON public.regulatory_alerts USING btree (org_implementation_deadline);
CREATE INDEX idx_alerts_org_status ON public.regulatory_alerts USING btree (org_id, alert_status);
CREATE INDEX idx_alerts_urgency ON public.regulatory_alerts USING btree (org_id, urgency_level);
CREATE INDEX idx_audit_org_time ON public.regulatory_audit_log USING btree (org_id, "timestamp");
CREATE INDEX idx_bank_assets_org_location ON public.bank_assets USING btree (org_id, h3_cell);
CREATE INDEX idx_bank_assets_org_sector ON public.bank_assets USING btree (org_id, sector);
CREATE INDEX idx_bank_assets_timestamp ON public.bank_assets USING btree (org_id, created_at);
CREATE INDEX idx_emissions_org_year ON public.ghg_emissions_inventory USING btree (org_id, reporting_year);
CREATE INDEX idx_filings_org_date ON public.regulatory_filings USING btree (org_id, submission_date);
CREATE INDEX idx_filings_org_status ON public.regulatory_filings USING btree (org_id, status);
CREATE INDEX idx_hazard_org_risk ON public.climate_hazard_exposure USING btree (org_id, physical_risk_score);
CREATE INDEX idx_hazard_org_type ON public.climate_hazard_exposure USING btree (org_id, hazard_type);
CREATE INDEX idx_notifications_org_unread ON public.dashboard_notifications USING btree (org_id, is_read);
CREATE INDEX idx_notifications_type ON public.dashboard_notifications USING btree (notification_type);
CREATE INDEX idx_regulatory_changes_deadline ON public.regulatory_changes USING btree (implementation_deadline);
CREATE INDEX idx_regulatory_changes_status ON public.regulatory_changes USING btree (status);
CREATE INDEX idx_risk_scores_org_category ON public.climate_risk_scores USING btree (org_id, risk_category);
CREATE INDEX idx_scenario_impact_material ON public.scenario_financial_impact USING btree (org_id, is_material);
CREATE INDEX idx_scenario_impact_org ON public.scenario_financial_impact USING btree (org_id, scenario_id);
ALTER TABLE ONLY public.bank_assets
    ADD CONSTRAINT bank_assets_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.climate_hazard_exposure
    ADD CONSTRAINT climate_hazard_exposure_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.bank_assets(asset_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.climate_hazard_exposure
    ADD CONSTRAINT climate_hazard_exposure_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.climate_risk_scores
    ADD CONSTRAINT climate_risk_scores_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.bank_assets(asset_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.climate_risk_scores
    ADD CONSTRAINT climate_risk_scores_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.dashboard_notifications
    ADD CONSTRAINT dashboard_notifications_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES public.regulatory_alerts(alert_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.dashboard_notifications
    ADD CONSTRAINT dashboard_notifications_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.filing_amendments
    ADD CONSTRAINT filing_amendments_filing_id_fkey FOREIGN KEY (filing_id) REFERENCES public.regulatory_filings(filing_id);
ALTER TABLE ONLY public.ghg_emissions_inventory
    ADD CONSTRAINT ghg_emissions_inventory_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.bank_assets(asset_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.ghg_emissions_inventory
    ADD CONSTRAINT ghg_emissions_inventory_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.governance_structure
    ADD CONSTRAINT governance_structure_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.kpi_summary
    ADD CONSTRAINT kpi_summary_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.org_crcs_subscription
    ADD CONSTRAINT org_crcs_subscription_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.org_module_subscriptions
    ADD CONSTRAINT org_module_subscriptions_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_active_version_id_fkey FOREIGN KEY (active_version_id) REFERENCES public.regulation_versions(version_id);
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id);
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id);
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_previous_version_id_fkey FOREIGN KEY (previous_version_id) REFERENCES public.regulation_versions(version_id);
ALTER TABLE ONLY public.regulation_versions
    ADD CONSTRAINT regulation_versions_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id);
ALTER TABLE ONLY public.regulatory_alerts
    ADD CONSTRAINT regulatory_alerts_change_id_fkey FOREIGN KEY (change_id) REFERENCES public.regulatory_changes(change_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_alerts
    ADD CONSTRAINT regulatory_alerts_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id);
ALTER TABLE ONLY public.regulatory_alerts
    ADD CONSTRAINT regulatory_alerts_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_audit_log
    ADD CONSTRAINT regulatory_audit_log_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_change_details
    ADD CONSTRAINT regulatory_change_details_change_id_fkey FOREIGN KEY (change_id) REFERENCES public.regulatory_changes(change_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_changes
    ADD CONSTRAINT regulatory_changes_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_amended_from_filing_id_fkey FOREIGN KEY (amended_from_filing_id) REFERENCES public.regulatory_filings(filing_id);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.regulation_versions(version_id);
ALTER TABLE ONLY public.scenario_financial_impact
    ADD CONSTRAINT scenario_financial_impact_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.bank_assets(asset_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.scenario_financial_impact
    ADD CONSTRAINT scenario_financial_impact_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.scenario_financial_impact
    ADD CONSTRAINT scenario_financial_impact_scenario_id_fkey FOREIGN KEY (scenario_id) REFERENCES public.climate_scenarios(scenario_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
