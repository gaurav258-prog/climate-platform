# REGULATORY MAINTENANCE ARCHITECTURE
## Continuous Regulatory Compliance System (CRCS)

**Status:** Design Phase  
**Support Model Name:** **Continuous Regulatory Compliance Service** (CRCS)  
**Core Principle:** All regulatory changes covered in subscription; modules charged annually

---

## PART 1: REGULATORY CHANGE DETECTION MODULE

### 1.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                   REGULATORY CHANGE DETECTION                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  Web Scrapers    │  │  News Feed       │  │  Manual      │  │
│  │  (Daily)         │  │  Aggregator      │  │  Submission  │  │
│  │                  │  │  (Real-time)     │  │  (Override)  │  │
│  │ • EUR-Lex        │  │                  │  │              │  │
│  │ • SEC.gov        │  │ • Reuters Legal  │  │ • Internal   │  │
│  │ • FCA website    │  │ • Bloomberg      │  │   team flag  │  │
│  │ • ECB decisions  │  │ • Regulatory     │  │              │  │
│  │ • National regs  │  │   news services  │  │              │  │
│  └─────────┬────────┘  └────────┬─────────┘  └────────┬─────┘  │
│            │                    │                     │         │
│            └────────────────────┼─────────────────────┘         │
│                                 │                               │
│                         ┌───────▼────────┐                      │
│                         │  Document      │                      │
│                         │  Ingestion     │                      │
│                         │  & Parsing     │                      │
│                         └───────┬────────┘                      │
│                                 │                               │
│                         ┌───────▼────────┐                      │
│                         │  Change        │                      │
│                         │  Detection &   │                      │
│                         │  Analysis      │                      │
│                         │  (Diff Engine) │                      │
│                         └───────┬────────┘                      │
│                                 │                               │
│                 ┌───────────────┼───────────────┐               │
│                 │               │               │               │
│         ┌───────▼──────┐ ┌─────▼───────┐ ┌────▼──────┐        │
│         │ Confirm      │ │ Impact      │ │ Build     │        │
│         │ Change       │ │ Analysis    │ │ Change    │        │
│         │ (Manual)     │ │ (Auto)      │ │ Report    │        │
│         └───────┬──────┘ └─────┬───────┘ └────┬──────┘        │
│                 │               │              │               │
│                 └───────────────┼──────────────┘               │
│                                 │                               │
│                 ┌───────────────▼──────────────┐               │
│                 │ Customer Notification        │               │
│                 │ Dashboard & Timeline         │               │
│                 │ (External-facing)            │               │
│                 └──────────────────────────────┘               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Data Model for Change Detection

```sql
-- Core regulatory change tracking
CREATE TABLE regulatory_changes (
  change_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  -- Change identification
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  old_version VARCHAR(50),  -- e.g., '2024'
  new_version VARCHAR(50),  -- e.g., '2025'
  
  -- Source & detection
  change_source VARCHAR(100),  -- 'EUR-Lex', 'SEC.gov', 'FCA', 'ECB', 'Manual'
  source_document_url TEXT,
  source_document_text JSONB,  -- Full text of regulation
  
  detection_method VARCHAR(50),  -- 'web_scraper', 'news_feed', 'manual'
  detected_date TIMESTAMP WITH TIME ZONE,
  detected_by_system BOOLEAN DEFAULT TRUE,
  confirmed_date TIMESTAMP WITH TIME ZONE,
  confirmed_by VARCHAR(255),  -- Internal analyst
  
  -- Regulatory timeline
  publication_date DATE,
  official_effective_date DATE,  -- When regulator says it's effective
  implementation_deadline DATE,  -- When it becomes mandatory
  
  -- Change classification
  change_type VARCHAR(50),  -- 'field_addition', 'calculation_change', 'new_requirement'
  change_classification VARCHAR(50),  -- 'Change' or 'Module'
  
  -- Impact assessment (auto-generated)
  affected_tables JSONB,  -- ['bank_assets', 'ghg_emissions_inventory']
  affected_processing_modules JSONB,  -- ['eba_credit_risk_scorer', 'scenario_modeler']
  affected_outputs JSONB,  -- ['TCFD_disclosure', 'COREP_Module_7']
  
  -- Change scope
  breaking_change BOOLEAN,  -- If true, must upgrade (no backward compat)
  backward_compatible BOOLEAN,
  data_migration_required BOOLEAN,
  
  -- Development effort estimate
  estimated_dev_hours INT,
  estimated_test_hours INT,
  estimated_total_hours INT,
  estimated_release_date DATE,  -- When we plan to release
  
  -- Customer timeline
  customer_deadline DATE GENERATED ALWAYS AS (
    CASE 
      WHEN (implementation_deadline - estimated_release_date) >= INTERVAL '7 days' 
      THEN implementation_deadline + INTERVAL '7 days'
      ELSE implementation_deadline
    END
  ) STORED,
  urgency_flag BOOLEAN,  -- TRUE if <4 weeks between detection and deadline
  
  -- Status tracking
  status VARCHAR(50),  -- 'Detected', 'Confirmed', 'Under Analysis', 'In Development', 'Testing', 'Ready for Release', 'Released'
  status_updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  -- Module determination
  is_new_module BOOLEAN,
  module_name VARCHAR(255),
  module_pricing_tier VARCHAR(50),  -- 'Standard', 'Premium', 'New_Module'
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  UNIQUE(framework_id, old_version, new_version)
);

-- Detailed change breakdown
CREATE TABLE regulatory_change_details (
  detail_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  change_id UUID NOT NULL REFERENCES regulatory_changes(change_id) ON DELETE CASCADE,
  
  -- Specific change
  article_or_section VARCHAR(255),  -- e.g., 'Article 8(2)', 'Section 1500'
  old_requirement TEXT,
  new_requirement TEXT,
  requirement_changed TEXT,
  
  -- Impact on system
  affects_data_model BOOLEAN,
  data_field_name VARCHAR(255),
  field_type_change VARCHAR(100),  -- 'new_field', 'type_change', 'deprecated'
  
  affects_processing_logic BOOLEAN,
  processing_change_description TEXT,
  calculation_methodology_changed BOOLEAN,
  
  affects_output_format BOOLEAN,
  output_change_description TEXT,
  
  -- Mitigation
  mitigation_strategy TEXT,
  breaking_change_mitigation TEXT,  -- How to handle backward compat
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Change analysis work log (internal tracking)
CREATE TABLE change_analysis_log (
  log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  change_id UUID NOT NULL REFERENCES regulatory_changes(change_id) ON DELETE CASCADE,
  
  -- Analysis step
  step_number INT,
  step_name VARCHAR(100),  -- 'Initial Detection', 'Impact Assessment', 'Dev Estimation', 'Ready for Dev'
  step_status VARCHAR(50),  -- 'In Progress', 'Completed', 'Blocked'
  step_owner VARCHAR(255),  -- Team member responsible
  
  -- Work log
  description TEXT,
  findings JSONB,
  blockers TEXT,
  
  completed_date TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 1.3 Change Detection Implementation (Python Service)

```python
# services/regulatory_monitoring/change_detector.py

class RegulatoryChangeDetector:
    """
    Automated system to detect, analyze, and track regulatory changes
    across all frameworks (TCFD, Taxonomy, SEC, Basel, EBA, FCA)
    """
    
    def __init__(self):
        self.scrapers = {
            'eur_lex': EurLexScraper(),
            'sec_gov': SECGovScraper(),
            'fca': FCAScraper(),
            'ecb': ECBScraper(),
            'national_regulators': NationalRegulatorScraper()
        }
        self.news_aggregator = RegulatoryNewsAggregator()
        self.document_analyzer = DocumentAnalyzer()
    
    async def run_daily_monitoring(self):
        """Daily task: monitor all sources for changes"""
        changes_detected = []
        
        # Scrape official sources
        for source_name, scraper in self.scrapers.items():
            try:
                new_documents = await scraper.fetch_latest()
                for doc in new_documents:
                    if self._is_new_or_updated(doc):
                        changes_detected.append({
                            'source': source_name,
                            'document': doc,
                            'detected_at': datetime.now()
                        })
            except Exception as e:
                logger.error(f"Scraper {source_name} failed: {e}")
        
        # Monitor news feeds
        news_items = await self.news_aggregator.fetch_regulatory_news()
        for item in news_items:
            if self._is_relevant_to_frameworks(item):
                changes_detected.append({
                    'source': 'news_feed',
                    'document': item,
                    'detected_at': datetime.now()
                })
        
        # Store detected changes
        for change in changes_detected:
            await self._store_detected_change(change)
        
        logger.info(f"Daily monitoring: {len(changes_detected)} potential changes detected")
        return changes_detected
    
    async def analyze_confirmed_change(self, change_id: UUID):
        """
        When a change is confirmed by internal analyst:
        1. Perform detailed impact analysis
        2. Estimate development timeline
        3. Generate customer notification
        """
        change = await db.get_regulatory_change(change_id)
        
        # Step 1: Document comparison (old vs. new regulation)
        old_reg_text = change.source_document_text  # Stored from detection
        new_reg_text = await self._fetch_full_regulation_text(change.framework_id, change.new_version)
        
        diff_analysis = self.document_analyzer.detailed_diff(old_reg_text, new_reg_text)
        
        # Step 2: Impact assessment
        impact_report = self._generate_impact_report(change, diff_analysis)
        # - Affected tables: which DB tables need schema changes
        # - Affected modules: which processing modules need code changes
        # - Affected outputs: which reports/disclosures affected
        
        # Step 3: Development effort estimation
        dev_estimate = self._estimate_development_effort(impact_report)
        # - Schema changes: X hours
        # - Processing logic: Y hours
        # - Testing: Z hours
        # - Total: X+Y+Z hours
        
        # Step 4: Determine if this is a new module
        is_new_module = self._classify_as_module(impact_report)
        
        # Step 5: Calculate customer deadline
        customer_deadline = self._calculate_customer_deadline(
            change.implementation_deadline,
            dev_estimate['total_hours'],
            dev_estimate['release_date']
        )
        
        # Step 6: Store analysis in DB
        await db.update_regulatory_change({
            'change_id': change_id,
            'status': 'Ready for Development',
            'estimated_dev_hours': dev_estimate['dev_hours'],
            'estimated_test_hours': dev_estimate['test_hours'],
            'estimated_release_date': dev_estimate['release_date'],
            'customer_deadline': customer_deadline,
            'affected_tables': impact_report['tables'],
            'affected_processing_modules': impact_report['modules'],
            'is_new_module': is_new_module,
            'impact_report': impact_report
        })
        
        return {
            'change_id': change_id,
            'impact_report': impact_report,
            'customer_deadline': customer_deadline,
            'is_new_module': is_new_module
        }
    
    def _calculate_customer_deadline(self, regulatory_deadline: date, est_hours: int, release_date: date) -> date:
        """
        Customer deadline = regulatory deadline + 7 days
        UNLESS: development finishes too close to deadline
        """
        buffer_deadline = regulatory_deadline + timedelta(days=7)
        
        if (regulatory_deadline - release_date).days < 28:
            # Less than 4 weeks - skip buffer, release immediately after internal confirmation
            return release_date
        else:
            return buffer_deadline
    
    def _classify_as_module(self, impact_report: dict) -> bool:
        """
        Decision: is this a new MODULE or just a CHANGE?
        
        MODULE = creates entirely new reporting function
        CHANGE = everything else (new field, new calculation, new data input)
        """
        # Check if this introduces entirely new output/report type
        new_outputs = impact_report.get('new_outputs', [])
        
        # New reporting functions: Product Governance, Green Finance Taxonomy, etc.
        new_reporting_functions = [
            'new_regulatory_report_type',
            'new_data_aggregation_framework',
            'new_disclosure_category'
        ]
        
        return any(func in impact_report['impact_type'] for func in new_reporting_functions)
    
    async def notify_customers(self, change_id: UUID):
        """
        Generate customer-facing notification:
        - Change detected
        - Regulatory deadline
        - Our deadline to you (regulatory deadline + 7 days, or earlier if tight)
        - Estimated deployment timeline
        - Impact on your workflows
        """
        change = await db.get_regulatory_change(change_id)
        
        notification = {
            'framework': change.framework_id,
            'change': change.new_version,
            'regulatory_deadline': change.implementation_deadline,
            'your_deadline': change.customer_deadline,
            'status': change.status,
            'affected_modules': change.affected_processing_modules,
            'is_new_module': change.is_new_module,
            'module_name': change.module_name if change.is_new_module else None,
            'estimated_release': change.estimated_release_date
        }
        
        # Send to customer portal (visible on dashboard)
        await self._update_customer_portal(change.framework_id, notification)
        
        # Email notification if deadline critical (<4 weeks)
        if change.urgency_flag:
            await self._send_email_notification(change.framework_id, notification)
        
        return notification

# Pricing decision based on module classification
def get_pricing_for_change(change: RegulatoryChange) -> dict:
    """
    Determine if change is covered in subscription or needs module charge
    """
    if change.is_new_module:
        return {
            'coverage': 'New Module - Annual Subscription Add-on',
            'included_in_CRCS': False,
            'pricing_model': 'Annual subscription add-on (negotiated per module)',
            'billing_start': 'Following Q1 discovery and annual contract renewal'
        }
    else:
        return {
            'coverage': 'Continuous Regulatory Compliance Service (CRCS)',
            'included_in_CRCS': True,
            'pricing_model': 'Included in subscription',
            'cost_to_customer': 0
        }
```

---

## PART 2: VERSION MANAGEMENT (N-1 SUPPORT)

### 2.1 Versioning Schema

```sql
-- Regulation versioning
CREATE TABLE regulation_versions (
  version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  
  -- Version identifier
  version_number VARCHAR(50) NOT NULL,  -- e.g., '2024', '2025'
  version_label VARCHAR(100),  -- e.g., 'EBA/GL/2025/01'
  
  -- Timeline
  published_date DATE,
  effective_date DATE,
  end_of_life_date DATE,  -- When support ends (6 months after next version)
  
  -- Support status
  support_status VARCHAR(50),  -- 'Current' (N), 'Legacy' (N-1), 'End of Life' (N-2+)
  is_current BOOLEAN,
  
  -- Schema version
  schema_snapshot JSONB,  -- Snapshot of DB schema for this version
  processing_logic_version VARCHAR(50),  -- Code version
  output_format_version VARCHAR(50),
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Customer's chosen regulation version (per framework)
CREATE TABLE org_regulation_version_preference (
  preference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id),
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  
  -- Version choice
  active_version_id UUID REFERENCES regulation_versions(version_id),
  previous_version_id UUID REFERENCES regulation_versions(version_id),
  
  -- Immutability rule (per framework)
  immutability_rule VARCHAR(50),  -- 'immutable', 'mutable', 'mutable_with_audit_trail'
  
  -- Timeline
  version_switched_date TIMESTAMP WITH TIME ZONE,
  end_of_support_date DATE,  -- When previous version stops being supported
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  UNIQUE(org_id, framework_id)
);

-- Regulatory filing versioning (immutability per framework)
CREATE TABLE regulatory_filings_v2 (
  filing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id),
  framework_id UUID NOT NULL REFERENCES regulatory_frameworks(framework_id),
  version_id UUID NOT NULL REFERENCES regulation_versions(version_id),
  
  -- Filing metadata
  filing_type VARCHAR(100),  -- 'Annual TCFD', 'Taxonomy Disclosure', 'SEC Form 10-K'
  reporting_period_start DATE,
  reporting_period_end DATE,
  
  -- Version tracking
  filing_version INT DEFAULT 1,  -- v1, v2 (amendment), v3, etc.
  is_amended BOOLEAN DEFAULT FALSE,
  amended_from_filing_id UUID REFERENCES regulatory_filings_v2(filing_id),
  amendment_reason TEXT,  -- Why was this amended?
  
  -- Immutability status
  is_immutable BOOLEAN,  -- Per framework setting
  
  -- Status
  status VARCHAR(50),  -- 'Draft', 'Submitted', 'Accepted', 'Amended'
  submission_date TIMESTAMP WITH TIME ZONE,
  
  -- Archive
  archive_status VARCHAR(50),  -- 'Live', 'Legacy Support', 'Archived'
  archive_date TIMESTAMP WITH TIME ZONE,  -- When moved to archive
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Amendment history (if mutable frameworks)
CREATE TABLE filing_amendments (
  amendment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filing_id UUID NOT NULL REFERENCES regulatory_filings_v2(filing_id),
  
  amendment_version INT,
  amendment_date TIMESTAMP WITH TIME ZONE,
  amendment_reason TEXT,
  
  old_values JSONB,  -- Previous values
  new_values JSONB,  -- Updated values
  amended_by VARCHAR(255),  -- Who approved the amendment
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 2.2 Version Lifecycle Management

```python
# services/versioning/version_manager.py

class VersionManager:
    """
    Manages regulation version lifecycle: Current (N) → Legacy (N-1) → End of Life
    """
    
    async def promote_new_version_to_current(self, new_version_id: UUID):
        """
        When new regulation version launches:
        1. Current (N) becomes Legacy (N-1)
        2. Previous Legacy (N-1) becomes End of Life
        3. New version becomes Current (N)
        4. Notify customers of support window
        """
        
        # Get current and legacy versions
        current = await db.get_current_regulation_version(framework_id)
        legacy = await db.get_legacy_regulation_version(framework_id)
        
        # Timeline: when does each version lose support?
        today = date.today()
        six_months_from_now = today + timedelta(days=180)
        
        # Update version statuses
        if legacy:
            await db.update_regulation_version(legacy.version_id, {
                'support_status': 'End of Life',
                'end_of_life_date': six_months_from_now
            })
        
        await db.update_regulation_version(current.version_id, {
            'support_status': 'Legacy',
            'is_current': False,
            'end_of_life_date': six_months_from_now
        })
        
        await db.update_regulation_version(new_version_id, {
            'support_status': 'Current',
            'is_current': True
        })
        
        # Notify customers
        await self._notify_customers_version_change(
            framework_id,
            current.version_number,
            new_version_id.version_number,
            six_months_from_now
        )
        
        logger.info(f"Version promotion complete: {new_version_id}")
    
    async def check_version_expiration(self):
        """Daily task: check if any versions are reaching end of life"""
        today = date.today()
        
        # Find versions ending support in 30 days
        expiring_versions = await db.query("""
            SELECT version_id, framework_id, version_number, end_of_life_date
            FROM regulation_versions
            WHERE end_of_life_date = TODAY() + INTERVAL '30 days'
            AND support_status = 'End of Life'
        """)
        
        for version in expiring_versions:
            # Notify customers using this version
            affected_orgs = await db.get_orgs_using_version(version.version_id)
            
            for org in affected_orgs:
                await self._send_migration_notification(
                    org.org_id,
                    version.framework_id,
                    version.version_number,
                    version.end_of_life_date
                )
        
        logger.info(f"Version expiration check: {len(expiring_versions)} versions expiring soon")
```

---

## PART 3: SUBSCRIPTION & MODULE MANAGEMENT

### 3.1 Subscription Tiers

```sql
-- CRCS Subscription Tier (All customers have this)
CREATE TABLE org_crcs_subscription (
  subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  
  -- Subscription details
  subscription_tier VARCHAR(50) DEFAULT 'Continuous Regulatory Compliance Service',
  coverage_description TEXT,
  -- "All regulatory changes covered in subscription. 
  --  Changes to existing functionality (new fields, calculation updates, 
  --  new mandatory data inputs) included. 
  --  New reporting functions/modules charged separately as annual add-ons."
  
  -- Billing
  annual_crcs_cost_eur DECIMAL(15, 2),  -- Base CRCS fee
  billing_start_date DATE,
  billing_end_date DATE,
  
  -- Coverage limits (not tiers, but informational)
  max_frameworks_covered INT,  -- Usually all
  change_coverage_included VARCHAR(255),  -- "Up to 80 changes/year" (informational only)
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  UNIQUE(org_id)
);

-- Optional modules (annual add-ons, discovered Q1 each year)
CREATE TABLE org_module_subscriptions (
  module_sub_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id) ON DELETE CASCADE,
  
  -- Module details
  module_id UUID NOT NULL,  -- References new regulatory modules
  module_name VARCHAR(255),  -- e.g., 'FCA Product Governance Reporting'
  module_description TEXT,
  
  -- Billing
  annual_module_cost_eur DECIMAL(15, 2),
  billing_start_date DATE,
  billing_end_date DATE,
  
  -- Subscription status
  status VARCHAR(50),  -- 'Active', 'Inactive', 'Paused'
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  UNIQUE(org_id, module_id)
);

-- Module discovery process (Q1 annual)
CREATE TABLE module_discovery_process (
  discovery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  discovery_year INT,
  discovery_quarter INT,  -- Q1 (Jan-Mar)
  
  -- Modules discovered this cycle
  modules_proposed JSONB,  -- List of new modules identified
  -- Example: [
  --   {name: 'FCA Product Governance', description: '...', estimated_cost: 15000},
  --   {name: 'EU Green Finance Taxonomy', description: '...', estimated_cost: 12000}
  -- ]
  
  -- Customer communication
  announcement_date DATE,
  available_for_subscription_from DATE,
  billing_effective_date DATE,
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## PART 4: JURISDICTION-BASED ARCHIVE RETENTION

### 4.1 Retention Rules by Jurisdiction

```sql
-- Archive retention rules per jurisdiction
CREATE TABLE archive_retention_rules (
  rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  
  country_code VARCHAR(2),  -- ISO 3166-1
  jurisdiction_name VARCHAR(100),
  
  -- Retention requirements
  default_retention_years INT,  -- e.g., 7 for EU, 10 for US
  framework_retention JSONB,  -- Per-framework rules
  -- Example: {
  --   "TCFD": 7,
  --   "EU_Taxonomy": 7,
  --   "SEC": 10,
  --   "Basel_III": 10
  -- }
  
  regulatory_reference TEXT,  -- Citation to regulation
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Customer's jurisdiction-based retention settings
CREATE TABLE org_archive_retention_settings (
  setting_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id UUID NOT NULL REFERENCES organizations(org_id),
  
  -- Jurisdiction(s)
  primary_jurisdiction VARCHAR(2),  -- Where customer is based
  secondary_jurisdictions JSONB,  -- Other relevant jurisdictions
  
  -- Retention rules applied
  applicable_retention_rules JSONB,  -- Rules from archive_retention_rules
  
  -- Extended retention (customer pays for this)
  extended_retention_years INT,  -- If customer needs longer than default
  extended_retention_cost_eur DECIMAL(15, 2),
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  UNIQUE(org_id)
);

-- Archive lifecycle management
CREATE TABLE regulatory_filing_archive (
  archive_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  filing_id UUID NOT NULL REFERENCES regulatory_filings_v2(filing_id),
  
  -- Archive details
  archived_date TIMESTAMP WITH TIME ZONE,
  archive_reason VARCHAR(50),  -- 'Version Deprecated', 'N-1 Support Ended', 'Retention Expired'
  
  -- Retention
  required_retention_until DATE,  -- Based on jurisdiction rules
  jurisdiction_applied VARCHAR(2),
  
  -- Storage
  archive_location VARCHAR(255),  -- S3 path, database reference, etc.
  is_retrievable BOOLEAN DEFAULT TRUE,  -- Can be retrieved if needed
  retrieval_cost_eur DECIMAL(15, 2),  -- If customer requests archival retrieval
  
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## PART 5: CUSTOMER NOTIFICATION & DASHBOARD

### 5.1 Customer Portal Display

```python
# Customer sees this on dashboard when changes detected

REGULATORY_CHANGE_NOTIFICATION = {
    'framework': 'EBA/ECB Climate Risk Guidelines',
    'change_detected': {
        'new_version': 'EBA/GL/2025/XX',
        'detected_on': '2025-11-15',
        'source': 'ECB Official Publications',
        'change_summary': 'New requirement for Scope 3 credit exposure assessment'
    },
    'timeline': {
        'regulatory_deadline': '2026-01-11',
        'your_deadline': '2026-01-18',  # regulatory deadline + 7 days
        'our_estimated_release': '2025-12-15',
        'urgency': 'HIGH'  # Less than 4 weeks between detection and deadline
    },
    'impact': {
        'is_new_module': False,
        'affected_systems': ['Credit Risk Scorer', 'Stress Testing Module'],
        'affected_reports': ['EBA COREP Module 7'],
        'data_migration_required': False,
        'estimated_deployment_impact': 'Low - additive change'
    },
    'cost': {
        'included_in_subscription': True,
        'additional_cost': 0,
        'coverage': 'Continuous Regulatory Compliance Service'
    },
    'status': {
        'current_phase': 'In Development',
        'completion_percentage': 65,
        'next_milestone': 'Testing Phase (starts 2025-12-01)'
    }
}

NEW_MODULE_NOTIFICATION = {
    'framework': 'FCA Climate Disclosure Rules',
    'module_discovered': {
        'module_name': 'FCA Product Governance Climate Assessment',
        'detected_on': '2025-11-20',
        'announcement_date': '2025-11-20',
        'regulatory_deadline': '2026-06-01'
    },
    'timeline': {
        'your_decision_deadline': '2026-01-31',  # Q1 Module Discovery process
        'billing_starts': '2026-04-01',  # Effective next annual subscription period
        'our_delivery_date': '2026-03-01'
    },
    'details': {
        'description': 'New FCA requirement for climate risk assessment in product governance decisions',
        'new_reporting_capability': True,
        'affects_workflows': ['Product Development', 'Governance Committee Decisions'],
        'estimated_annual_cost': 25000,  # Per customer (variable)
        'why_separate_charge': 'Creates entirely new regulatory reporting function'
    },
    'next_steps': {
        'learn_more': 'Click to see full documentation',
        'indicate_interest': 'Select checkbox by Jan 31 to include in next subscription',
        'contact_sales': 'For pricing negotiation'
    }
}
```

---

## PART 6: IMPLEMENTATION ROADMAP FOR CRCS

### Phase 1: Foundation (Weeks 1-4)
- [ ] Build database schema (regulatory_changes, regulation_versions, archive_retention)
- [ ] Implement web scrapers (EUR-Lex, SEC, FCA, ECB)
- [ ] Build news feed aggregator
- [ ] Create document analysis engine (diff comparison)
- [ ] Implement change detection service (daily monitoring)

### Phase 2: Analysis & Notification (Weeks 3-6)
- [ ] Build impact analysis engine
- [ ] Implement development effort estimation
- [ ] Create customer notification dashboard
- [ ] Build regulatory change detection module UI
- [ ] Test with sample regulations

### Phase 3: Version Management (Weeks 5-8)
- [ ] Implement N-1 versioning system
- [ ] Build version promotion workflows
- [ ] Implement archive lifecycle management
- [ ] Add jurisdiction-based retention rules
- [ ] Create version migration tooling

### Phase 4: Module Management (Weeks 7-10)
- [ ] Build Q1 module discovery process
- [ ] Implement module subscription management
- [ ] Create module announcement system
- [ ] Build pricing configuration for modules
- [ ] Integrate with billing system

### Phase 5: Integration & Testing (Weeks 9-12)
- [ ] Integrate CRCS with existing regulatory processing
- [ ] End-to-end testing (detect change → analyze → develop → notify → deploy)
- [ ] Performance testing (handle multiple concurrent changes)
- [ ] Security review (regulatory data handling)
- [ ] Customer acceptance testing

---

## SUMMARY: CONTINUOUS REGULATORY COMPLIANCE SERVICE (CRCS)

**What's included:**
✅ All regulatory changes covered in subscription  
✅ Automated detection of regulatory updates (daily)  
✅ Impact analysis (which tables, modules, outputs affected)  
✅ Development & deployment (included)  
✅ Customer notification (regulatory deadline + 7 days, or sooner if tight)  
✅ N-1 version support (6 months)  
✅ Jurisdiction-based archive retention  

**What's charged separately:**
💰 New modules (discovered Q1 annually, billed as annual add-on)  
💰 Extended archive retention (if customer needs longer than jurisdiction default)  

**Support Model:**
- **One subscription tier** (CRCS) covering all changes
- **Annual module discovery** (Q1) — choose which modules to adopt
- **Transparent pricing** — customer knows cost of new modules upfront

---

This architecture ensures:
- ✅ Regulatory compliance doesn't surprise customers
- ✅ Predictable costs (changes covered, modules bundled Q1)
- ✅ Operational transparency (customers see status, timeline, impact)
- ✅ Continuity (N-1 support + jurisdiction-aware archival)
