-- Frozen DDL of the eleven legacy CRCS tables exactly as they stood at filing_views_20260928 (pg_dump -s of a
-- scratch database built to that revision) — what crcs_legacy_retire_20260928's downgrade restores (E25).
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
CREATE TABLE public.regulatory_document_snapshots (
    snapshot_id uuid NOT NULL,
    framework_id uuid NOT NULL,
    source_name character varying(60) NOT NULL,
    title character varying(500),
    url character varying(1000),
    published_date character varying(60),
    content text,
    content_hash character varying(64) NOT NULL,
    scraped_at timestamp with time zone DEFAULT now(),
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
ALTER TABLE ONLY public.dashboard_notifications
    ADD CONSTRAINT dashboard_notifications_pkey PRIMARY KEY (notification_id);
ALTER TABLE ONLY public.filing_amendments
    ADD CONSTRAINT filing_amendments_pkey PRIMARY KEY (amendment_id);
ALTER TABLE ONLY public.org_crcs_subscription
    ADD CONSTRAINT org_crcs_subscription_org_id_key UNIQUE (org_id);
ALTER TABLE ONLY public.org_crcs_subscription
    ADD CONSTRAINT org_crcs_subscription_pkey PRIMARY KEY (subscription_id);
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_org_id_framework_id_key UNIQUE (org_id, framework_id);
ALTER TABLE ONLY public.org_regulation_version_preference
    ADD CONSTRAINT org_regulation_version_preference_pkey PRIMARY KEY (preference_id);
ALTER TABLE ONLY public.regulation_versions
    ADD CONSTRAINT regulation_versions_framework_id_version_number_key UNIQUE (framework_id, version_number);
ALTER TABLE ONLY public.regulation_versions
    ADD CONSTRAINT regulation_versions_pkey PRIMARY KEY (version_id);
ALTER TABLE ONLY public.regulatory_alerts
    ADD CONSTRAINT regulatory_alerts_org_id_change_id_key UNIQUE (org_id, change_id);
ALTER TABLE ONLY public.regulatory_alerts
    ADD CONSTRAINT regulatory_alerts_pkey PRIMARY KEY (alert_id);
ALTER TABLE ONLY public.regulatory_change_details
    ADD CONSTRAINT regulatory_change_details_pkey PRIMARY KEY (detail_id);
ALTER TABLE ONLY public.regulatory_changes
    ADD CONSTRAINT regulatory_changes_framework_id_old_version_new_version_key UNIQUE (framework_id, old_version, new_version);
ALTER TABLE ONLY public.regulatory_changes
    ADD CONSTRAINT regulatory_changes_pkey PRIMARY KEY (change_id);
ALTER TABLE ONLY public.regulatory_document_snapshots
    ADD CONSTRAINT regulatory_document_snapshots_framework_id_source_name_key UNIQUE (framework_id, source_name);
ALTER TABLE ONLY public.regulatory_document_snapshots
    ADD CONSTRAINT regulatory_document_snapshots_pkey PRIMARY KEY (snapshot_id);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_org_id_framework_id_reporting_period_end_key UNIQUE (org_id, framework_id, reporting_period_end);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_pkey PRIMARY KEY (filing_id);
ALTER TABLE ONLY public.regulatory_frameworks
    ADD CONSTRAINT regulatory_frameworks_framework_name_key UNIQUE (framework_name);
ALTER TABLE ONLY public.regulatory_frameworks
    ADD CONSTRAINT regulatory_frameworks_pkey PRIMARY KEY (framework_id);
CREATE INDEX idx_alerts_deadline ON public.regulatory_alerts USING btree (org_implementation_deadline);
CREATE INDEX idx_alerts_org_status ON public.regulatory_alerts USING btree (org_id, alert_status);
CREATE INDEX idx_alerts_urgency ON public.regulatory_alerts USING btree (org_id, urgency_level);
CREATE INDEX idx_filings_org_date ON public.regulatory_filings USING btree (org_id, submission_date);
CREATE INDEX idx_filings_org_status ON public.regulatory_filings USING btree (org_id, status);
CREATE INDEX idx_notifications_org_unread ON public.dashboard_notifications USING btree (org_id, is_read);
CREATE INDEX idx_notifications_type ON public.dashboard_notifications USING btree (notification_type);
CREATE INDEX idx_regulatory_changes_deadline ON public.regulatory_changes USING btree (implementation_deadline);
CREATE INDEX idx_regulatory_changes_status ON public.regulatory_changes USING btree (status);
ALTER TABLE ONLY public.dashboard_notifications
    ADD CONSTRAINT dashboard_notifications_alert_id_fkey FOREIGN KEY (alert_id) REFERENCES public.regulatory_alerts(alert_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.dashboard_notifications
    ADD CONSTRAINT dashboard_notifications_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.filing_amendments
    ADD CONSTRAINT filing_amendments_filing_id_fkey FOREIGN KEY (filing_id) REFERENCES public.regulatory_filings(filing_id);
ALTER TABLE ONLY public.org_crcs_subscription
    ADD CONSTRAINT org_crcs_subscription_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
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
ALTER TABLE ONLY public.regulatory_change_details
    ADD CONSTRAINT regulatory_change_details_change_id_fkey FOREIGN KEY (change_id) REFERENCES public.regulatory_changes(change_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_changes
    ADD CONSTRAINT regulatory_changes_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id);
ALTER TABLE ONLY public.regulatory_document_snapshots
    ADD CONSTRAINT regulatory_document_snapshots_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_amended_from_filing_id_fkey FOREIGN KEY (amended_from_filing_id) REFERENCES public.regulatory_filings(filing_id);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_framework_id_fkey FOREIGN KEY (framework_id) REFERENCES public.regulatory_frameworks(framework_id);
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_org_id_fkey FOREIGN KEY (org_id) REFERENCES public.organizations(org_id) ON DELETE CASCADE;
ALTER TABLE ONLY public.regulatory_filings
    ADD CONSTRAINT regulatory_filings_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.regulation_versions(version_id);
