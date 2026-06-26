# PHASED IMPLEMENTATION ROADMAP
## Climate Intelligence Platform - RegTech Build Plan

**Status:** Foundation complete (regulatory research + database schema)  
**Current Date:** 2026-06-26  
**Critical Deadline:** Jan 11, 2026 (EBA/GL/2025/01) — **6 months away**

---

## REGULATORY COMPLIANCE PRIORITY

Based on **binding vs. optional** status:

### **TIER 1: BINDING + ENFORCEABLE (Highest Priority)**
- ✅ **EU Taxonomy Regulation** — Active enforcement, penalties €250K-€7.5M+
- ✅ **EU EBA/ECB Guidelines** — Jan 11, 2026 deadline, ECB actively penalizing non-compliance
- ✅ **UK FCA Climate Rules** — Active enforcement, £5B+ AUM threshold

### **TIER 2: BINDING + TRANSITIONING (High Priority)**
- ✅ **TCFD Framework** — Voluntary now, mandatory in EU/UK/US (2025-2027)
- ✅ **UK SRS Implementation** — Mandatory Jan 1, 2027 (replaces TCFD)

### **TIER 3: CONDITIONAL (Medium Priority)**
- ⚠️ **SEC Climate Rules** — Legally STAYED pending litigation, June 2026 decision pending
- ⚠️ **Basel III Climate** — Principle-based guidance only, no fixed capital charges

---

## PHASED DELIVERY PLAN

### **PHASE 1: EBA/ECB Compliance (Weeks 1-6)** ⚡ URGENT
**Deadline:** Jan 11, 2026 (implement ESG risk framework)  
**Target:** Large EU banks (€30B+ assets) + ECB-supervised entities

**Deliverables:**
1. **Credit Risk Assessment Module**
   - Asset classification by climate exposure (physical + transition)
   - Loan origination climate risk scoring
   - Portfolio concentration risk analysis

2. **NGFS Scenario Execution**
   - Implement 5 NGFS climate pathways (orderly, disorderly, hot house world)
   - 3-5 year stress testing for capital adequacy (ICAAP/ILAAP)
   - PD/LGD adjustments for climate-exposed counterparties

3. **Governance & Reporting**
   - Climate risk management policy documentation
   - Stress test results reporting format
   - Compliance attestation (for Jan 11 deadline)

**Effort:** 80 hours  
**Team:** 2-3 engineers (backend processing layer)  
**Success Criteria:** Can generate EBA COREP Module 7 stress test results

---

### **PHASE 2: EU Taxonomy Compliance (Weeks 4-8)**
**Deadline:** Ongoing (active enforcement)  
**Target:** Banks, asset managers, insurers reporting asset alignment

**Deliverables:**
1. **Activity Classification Engine**
   - NACE code mapping
   - "Taxonomy-aligned" vs. "eligible" vs. "non-aligned" classification
   - Revenue/CapEx/OpEx breakdown by activity

2. **DNSH Assessment Module**
   - Climate mitigation resilience check (>90% effectiveness)
   - Physical risk assessment (>2°C warming scenarios)
   - Environmental thresholds (water stress, pollution, biodiversity)

3. **KPI Calculation**
   - Turnover % aligned formula
   - CapEx % aligned formula
   - OpEx % aligned formula
   - XBRL output generation

**Effort:** 120 hours  
**Team:** 2-3 engineers (data pipeline + calculation engine)  
**Success Criteria:** Generate XBRL reports with Taxonomy KPIs

---

### **PHASE 3: TCFD + FCA Compliance (Weeks 7-12)**
**Deadline:** Annual reporting (FCA £5B+ AUM thresholds active)  
**Target:** Asset managers, listed companies, large financial institutions

**Deliverables:**
1. **Scenario Analysis Engine** (TCFD Foundation)
   - 1.5°C, 2°C, 4°C scenario modeling
   - NPV calculation with climate risk premiums
   - Stranded asset identification

2. **Financial Impact Quantification**
   - Revenue/cost/capex impact by scenario
   - Time horizon specific projections (short/medium/long-term)
   - Sensitivity analysis (carbon price, demand, physical events)

3. **FCA Asset Manager Metrics** (if applicable)
   - WACI calculation (Scope 1+2 / Revenue weighted by portfolio)
   - Carbon footprint (Scope 1+2 / €M invested)
   - Product-level metric reporting
   - Double materiality assessment

4. **TCFD Report Generation**
   - Governance narrative
   - Strategy narrative
   - Risk management narrative
   - Metrics & targets tables
   - Scenario resilience assessment

**Effort:** 180 hours  
**Team:** 3-4 engineers (complex financial modeling)  
**Success Criteria:** Generate complete TCFD disclosure report + FCA metrics

---

### **PHASE 4: SEC + Basel III Integration (Weeks 10-16)**
**Status:** Conditional on SEC litigation outcome (June 2026)  
**Target:** US subsidiaries of European banks (SEC rules affect them)

**Deliverables (SEC):**
1. **GHG Scope 3 Calculation**
   - Value chain emissions (supplier + product use + end-of-life)
   - Activity-based or spend-based modeling
   - Scope 3 materiality assessment

2. **Form 10-K Reporting**
   - Item 1500 climate risk disclosure
   - XBRL tagging
   - Attestation statement

**Deliverables (Basel III):**
1. **Stress Testing Framework**
   - PD adjustment for climate exposure by sector
   - LGD adjustment based on collateral physical risk
   - RWA impact calculation

2. **Pillar 2 Supervisory Add-on**
   - Capital charge determination (0.25%-1.0% CET1 depending on exposure)
   - Governance compliance self-assessment

**Effort:** 120 hours (SEC) + 100 hours (Basel III) = 220 hours  
**Team:** 3-4 engineers  
**Success Criteria:**
- SEC: Generate Form 10-K Item 1500 disclosure
- Basel III: Calculate climate-adjusted capital requirements

---

## TIMELINE OVERVIEW

```
WEEK 1-6:   ████████ PHASE 1: EBA/ECB (URGENT - Jan 11 deadline)
WEEK 4-8:   ████████ PHASE 2: EU Taxonomy
WEEK 7-12:  ████████ PHASE 3: TCFD + FCA
WEEK 10-16: ████████ PHASE 4: SEC + Basel III (conditional)

Total Duration: 16 weeks (4 months) for all phases
With overlaps: Realistic timeline is 14-18 weeks
```

---

## ARCHITECTURE LAYERS

All phases build on the **unified database schema** (already complete):

### **Layer 1: Data Input** (Reused across all phases)
- Bank asset inventory (table: `bank_assets`)
- Climate hazard exposure (table: `climate_hazard_exposure`)
- GHG emissions data (table: `ghg_emissions_inventory`)
- Bank portfolio data (table: `scenario_financial_impact`)

### **Layer 2: Processing Engines** (Phase-specific calculation modules)

**Phase 1 (EBA/ECB):**
```python
# services/processing/eba_processor.py
- classify_asset_climate_risk()
- calculate_pd_adjustment_climate()
- execute_ngfs_stress_test()
- generate_corep_module_7()
```

**Phase 2 (Taxonomy):**
```python
# services/processing/taxonomy_processor.py
- classify_activity_nace()
- assess_dnsh_criteria()
- calculate_alignment_kpis()
- generate_xbrl_report()
```

**Phase 3 (TCFD/FCA):**
```python
# services/processing/scenario_processor.py
- model_scenario_financials()
- calculate_npv_climate_adjusted()
- generate_tcfd_disclosures()
- calculate_waci_metrics()
```

**Phase 4 (SEC/Basel):**
```python
# services/processing/sec_basel_processor.py
- calculate_scope_3_emissions()
- generate_form_10k_item_1500()
- calculate_climate_rwa_impact()
```

### **Layer 3: Output Generators** (Template-based report creation)
- XBRL files (EU Taxonomy, SEC)
- PDF narratives (TCFD, FCA)
- CSV exports (stress test results, KPI summaries)
- Regulatory filing templates

---

## CRITICAL SUCCESS FACTORS

### **For Jan 11, 2026 EBA Deadline (Phase 1):**
✅ Complete credit risk classification module  
✅ NGFS scenario execution working  
✅ COREP Module 7 stress test output generated  
✅ Testing with sample portfolio (minimum 10 assets)  
✅ Documentation of methodology for ECB review  

### **For Ongoing Taxonomy Compliance (Phase 2):**
✅ NACE classification accuracy (>95% precision)  
✅ DNSH thresholds correctly applied  
✅ XBRL validation against EC schema  
✅ KPI calculation verified against templates  

### **For Annual TCFD/FCA Reporting (Phase 3):**
✅ Scenario modeling produces consistent results  
✅ Financial impact quantification realistic  
✅ Governance narrative complete  
✅ Report generation automated  

---

## RESOURCE PLAN

### **Team Composition**
- **1 Solution Architect** (oversee all phases, ensure consistency)
- **4-5 Backend Engineers** (processing logic + APIs)
- **1-2 Data Engineers** (ETL pipelines, data quality)
- **1 QA Engineer** (regulatory compliance testing)
- **1 Product Manager** (stakeholder management, timeline)

### **Total Effort**
- Phase 1: 80 hours
- Phase 2: 120 hours
- Phase 3: 180 hours
- Phase 4: 220 hours
- **Total: ~600 hours** = ~15 weeks @ 40 hours/week (with parallelization)

### **Infrastructure**
- PostgreSQL database (schema already created)
- Python FastAPI backend
- Celery for async processing
- Redis for caching
- Docker for containerization

---

## RISK MITIGATION

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| EBA deadline slip (Jan 11) | **HIGH** | **CRITICAL** | Start Phase 1 immediately, weekly progress checks |
| Regulatory guidance changes | Medium | High | Monitor ECB/EBA publications, maintain flexible schema |
| Data quality issues | Medium | High | Implement data validation layer, QA checklist |
| SEC litigation delays | Low | Medium | Plan Phase 4 for June 2026 decision, don't block earlier phases |
| Performance (large portfolios) | Medium | Medium | Index optimization, async processing, caching strategy |
| Scope creep | **HIGH** | High | Strict phase gates, frozen requirements per phase |

---

## SUCCESS METRICS

**Phase 1 (EBA):** ECB accepts compliance submission; no penalties  
**Phase 2 (Taxonomy):** XBRL files pass EC validation; no data quality issues  
**Phase 3 (TCFD/FCA):** Audit report validates narrative + quantitative disclosures  
**Phase 4 (SEC/Basel):** Capital calculations match regulatory expectations  

**Overall:** Platform supports 10+ banks with multi-framework compliance by end of Phase 3

---

## NEXT IMMEDIATE ACTIONS

1. **This Week:**
   - [ ] Spin up PostgreSQL + run DATABASE_SCHEMA_REGULATORY_V2.sql
   - [ ] Create ORM models (SQLAlchemy) for all 25 tables
   - [ ] Set up API skeleton (FastAPI)
   - [ ] Create test data loader (sample assets, emissions, scenarios)

2. **Next 2 Weeks:**
   - [ ] Build EBA asset classification module
   - [ ] Implement NGFS scenario parameters
   - [ ] Create stress test calculation engine
   - [ ] Generate first COREP Module 7 output

3. **Weeks 3-6:**
   - [ ] Complete Phase 1 testing + validation
   - [ ] Start Phase 2 NACE classifier + DNSH assessment
   - [ ] Parallel: Begin Phase 3 scenario modeling

---

## DOCUMENT LOCATION

📁 **All research & schemas:** `/Users/gauravsachdeva/Downloads/climate-platform/`

- `REGULATORY_MATRIX_FINAL.md` — Input/processing/output mapping
- `DATABASE_SCHEMA_REGULATORY_V2.sql` — Production schema (ready to deploy)
- `IMPLEMENTATION_ROADMAP_PHASED.md` — This document

📁 **Detailed research:** `/private/tmp/.../scratchpad/`

- `EXECUTIVE_SUMMARY_CLIMATE_DISCLOSURE_RESEARCH.md`
- `CLIMATE_DISCLOSURE_REGULATIONS_COMPREHENSIVE_REPORT.md`
- `EU_Taxonomy_Regulation_Research_Report.md`
- Plus 10+ framework-specific deep dives

---

**STATUS: Foundation complete. Ready for Phase 1 implementation. EBA deadline is 6 months away. Let's go.**
