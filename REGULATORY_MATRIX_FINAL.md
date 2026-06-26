# REGULATORY REQUIREMENTS MATRIX FOR REGTECH PLATFORM
## Final Compiled Version: Input Data → Processing Logic → Output Format

**Status:** Research Phase 1 Complete (TCFD comprehensive)  
**Research Phase 2:** In progress (EU Taxonomy, SEC, Basel III, EBA/ECB, FCA)  
**Geography:** Europe priority, Global scope  

---

# PART 1: TCFD RECOMMENDATIONS (GLOBAL BASELINE)
## Complete Regulatory Breakdown

### GOVERNANCE PILLAR

**Disclosure 1: Board Oversight**
- **Input Required:** Board structure, committee assignments, meeting minutes on climate topics
- **Processing:** Map board governance to climate risk responsibility
- **Output:** Narrative disclosure of board oversight mechanisms
- **Mandatory:** Yes (applies to all entities)

**Disclosure 2: Management's Role**
- **Input Required:** Management committee structure, climate responsibility assignments
- **Processing:** Document management's assessment and management processes
- **Output:** Narrative disclosure of management roles
- **Mandatory:** Yes (applies to all entities)

---

### STRATEGY PILLAR

**Disclosure 3a: Climate Risks & Opportunities (Short/Medium/Long-term)**
- **Input Required:**
  - Business model data by segment/geography
  - Climate hazard exposure maps (physical risks)
  - Policy/regulatory landscape analysis
  - Competitive/technology landscape
  - Time horizons: 0-1 yr (short), 1-5 yr (medium), 5+ yr (long)

- **Processing Logic:**
  - Identify material climate-related risks and opportunities
  - Map to business segments and time horizons
  - Assess likelihood and potential impact
  - No quantitative threshold specified (qualitative assessment acceptable)

- **Output Format:** Narrative table with risks/opportunities by time horizon
  - Risk type (physical or transition)
  - Description
  - Potential impact
  - Time horizon
  - Likelihood assessment

- **Materiality:** Subject to materiality assessment (not required if immaterial)

**Disclosure 3b: Impact on Business/Strategy/Financial Planning**
- **Input Required:** Business strategy documents, financial projections, capital allocation plans
- **Processing:** Analyze how climate risks integrate into business strategy
- **Output:** Narrative disclosure of strategic implications
- **Materiality:** Subject to materiality assessment

**Disclosure 3c: Climate Scenario Resilience Analysis**
- **Input Required:**
  - **MANDATORY Scenarios:**
    - Scenario A: 2°C or lower (Paris Agreement-aligned transition pathway)
    - Scenario B: 4°C+ (business-as-usual, high warming scenario)
  
  - **Scenario Parameters:**
    - Temperature pathway (IPCC RCP 2.6 for 2°C, RCP 8.5 for 4°C; or SSP equivalents)
    - Carbon pricing trajectory: €10-200/ton CO2e by 2050 (2°C scenario)
    - Technology cost evolution (renewable energy, batteries, efficiency)
    - Policy implementation timelines
    - Energy transition pace
  
  - **Time Horizons:**
    - Short-term: entity-specific planning cycle
    - Medium-term: 2030-2040 milestones
    - Long-term: 2050+ net-zero alignment
  
  - **Business Data:**
    - Revenue by business line and geography
    - Asset locations and climate hazard exposure
    - Supply chain vulnerabilities
    - Energy/resource intensity
    - Capital expenditure plans

- **Processing Logic:**

  **Step 1: Scenario-Based Financial Modeling**
  ```
  For each scenario {
    For each time horizon {
      For each business segment {
        Simulate cash flows under scenario conditions
        Adjust for: policy changes, technology costs, demand shifts, physical impacts
        Calculate NPV = Σ [CF_t / (1 + r + climate_risk_premium)^t]
          where: climate_risk_premium = 2-5% depending on exposure
      }
    }
  }
  ```

  **Step 2: Identify Strategic Implications**
  - Revenue impact: Market demand shifts, new market opportunities
  - Cost impact: Input costs, compliance costs, adaptation capex
  - Asset impairment: Stranded asset risk identification
  - Competitive positioning: Technology/market shifts

  **Step 3: Assess Resilience**
  - Business model viability under each scenario
  - Strategic vulnerability areas
  - Adaptation pathways and investments required

- **Output Format:**
  - Narrative: How organization is positioned for each scenario
  - Quantitative table: Key financial metrics by scenario
    - Revenue impact (%)
    - Profitability impact (%)
    - Capital expenditure requirements
    - NPV by scenario
  
  - Scenario resilience summary:
    - 2°C scenario: [Organization-specific resilience assessment]
    - 4°C scenario: [Organization-specific resilience assessment]

- **Materiality:** Subject to materiality assessment
- **Update Frequency:** Minimum every 5 years; annually if scenario assumptions change significantly

---

### RISK MANAGEMENT PILLAR

**Disclosure 4: Climate Risk Identification & Assessment**
- **Input Required:** Enterprise risk assessment methodology, historical data, stakeholder input
- **Processing:** Identify material climate-related risks using defined process
- **Output:** Narrative description of identification process
- **Mandatory:** Yes

**Disclosure 5: Climate Risk Management Processes**
- **Input Required:** Risk management policies, procedures, monitoring frameworks
- **Processing:** Document how identified risks are managed
- **Output:** Narrative description of management approach
- **Mandatory:** Yes

**Disclosure 6: Integration into Overall Risk Management**
- **Input Required:** Enterprise risk management framework, reporting structure
- **Processing:** Describe how climate risk integrates into overall ERM
- **Output:** Narrative disclosure
- **Mandatory:** Yes

---

### METRICS & TARGETS PILLAR

**Disclosure 7: Metrics to Assess & Manage Climate Risks**
- **Input Required:** Performance data, benchmarks, calculation methodologies
- **Processing:** Select metrics relevant to strategy and risk management
- **Output:** Annual metrics reporting with multi-year trends
- **Mandatory:** Yes (but metric selection flexible)

**Disclosure 8: Scope 1 & 2 GHG Emissions (MANDATORY)**
- **Input Required:** Energy bills, fuel consumption, purchased electricity data, operational records

- **Processing Logic:**

  **Scope 1 Emissions (Direct):** tCO2e from sources owned/controlled
  ```
  Scope 1 = Σ [Fuel consumption × Emission factor] + [Process emissions] + [Fugitive emissions]
  
  Calculation method: Operational control or equity share approach
  Emission factors: IPCC, EPA, or country-specific
  
  Common sources:
  - Fossil fuel combustion (gas, oil, coal): consumption × 2.35-3.15 kg CO2/unit
  - Refrigerant leakage: usage rate × GWP factor × 23-5,500x CO2
  - Process emissions: chemical reactions (cement, steel production)
  ```

  **Scope 2 Emissions (Indirect Energy):** tCO2e from purchased electricity/steam/heat/cooling
  ```
  Scope 2 = Σ [Energy purchased × Grid emission factor]
  
  Two methodologies:
  1. Location-based: using average grid carbon intensity
  2. Market-based: using contractual renewable energy certificates
  
  Both must be disclosed if renewable energy purchased
  ```

  **Scope 3 Emissions (Value Chain):** Only if material
  ```
  15 categories: upstream transportation, business travel, employee commuting, 
  use of sold products, end-of-life, etc.
  Calculation: Either spend-based or activity-based modeling
  Materiality threshold: If >5% of Scope 1+2, recommend disclosure
  ```

- **Output Format:**
  - **Table A1: GHG Emissions Summary (multi-year)**
    | Year | Scope 1 (tCO2e) | Scope 2 Location (tCO2e) | Scope 2 Market (tCO2e) | Total (tCO2e) |
    | ---- | --------------- | ----------------------- | ---------------------- | ------------- |
    | 2024 | [value]         | [value]                 | [value]                | [value]       |
    | 2023 | [value]         | [value]                 | [value]                | [value]       |

  - **Table A2: GHG Emissions by Location/Business Line** (if applicable)
  - **Scope 3:** If disclosed, table showing category breakdown
  - **Methodology statement:** Calculation approach, emission factors used, data quality

- **Materiality:** NO materiality exemption (Scope 1 & 2 mandatory for all)
- **Assurance:** Recommended (increasingly becoming mandatory through regulations)

**Disclosure 9: GHG Emissions Intensity & Targets**
- **Input Required:**
  - Baseline emissions and year
  - Target emissions and year
  - Target methodology (absolute, intensity-based, science-based)
  - Revenue/employees/production units for intensity calculation

- **Processing Logic:**

  **Intensity Metrics (Primary TCFD KPIs):**
  ```
  1. Carbon Intensity = [Scope 1 + 2 emissions (tCO2e)] / [Revenue (€M) or Production (units)]
     Unit: tCO2e / €M or tCO2e / unit produced
  
  2. Weighted Average Carbon Intensity (WACI) = Σ [Scope 1+2 emissions / Revenue] × [Portfolio weight]
     Application: Financial institutions (asset managers, asset owners)
     Unit: tCO2e / €M invested
  
  3. Science-Based Target = Reduction % by target year consistent with limiting warming to 1.5°C
     Typically: 50% reduction by 2030, Net Zero by 2050
  ```

  **Target-Setting Process:**
  - Baseline selection: Most recent complete year
  - Pathway selection: Absolute reduction or intensity-based
  - Validation: Against IPCC 1.5°C pathway
  - Update frequency: Minimum every 5 years

- **Output Format:**
  - **Table C1: GHG Emissions Targets**
    | Metric | Baseline | Baseline Year | Target | Target Year | Interim Milestones |
    | ------ | -------- | ------------- | ------ | ----------- | ------------------ |
    | Scope 1+2 absolute (tCO2e) | [val] | 2024 | [val] | 2050 | 2030: -50% |
    | Carbon intensity (tCO2e/€M) | [val] | 2024 | [val] | 2050 | 2030: [val] |
    | Renewable energy (%) | 25% | 2024 | 100% | 2050 | 2030: 60% |

  - **Narrative:** Target methodology, pathway alignment, progress tracking

- **Materiality:** NO materiality exemption (targets mandatory if climate risks identified)

---

## TCFD MATERIALITY ASSESSMENT FRAMEWORK

**Definition:** Information is material if its omission/misstatement could influence decisions of report users

**Applied To:**
- Strategy disclosures (Disclosures 3a, 3b, 3c)
- Metrics & Targets (part of Disclosure 9)

**NOT Applied To:**
- Governance (Disclosures 1, 2)
- Risk Management (Disclosures 4, 5, 6)
- Scope 1 & 2 emissions (Disclosure 8)
- GHG targets (Disclosure 9)

**Assessment Process:**
1. Analyze quantitative impact: Does climate risk affect >5% of earnings/cash flows?
2. Analyze qualitative impact: Could risk affect stakeholder decisions?
3. Professional judgment: Don't dismiss as immaterial based solely on time horizon
4. Document assessment: Maintain clear rationale for conclusions

**Threshold Guidance:**
- Large organizations (>$1B revenue): More robust scenario analysis required
- Significantly climate-exposed: In-depth quantitative analysis required
- Asset-heavy industries: Physical risk assessment mandatory
- Financial institutions: Financed emissions disclosure required

---

## TCFD SCENARIO ANALYSIS TECHNICAL SPECIFICATIONS

### Climate Pathways

**1.5°C Pathway (Strong Mitigation)**
- Peak warming: ~1.5°C above pre-industrial by mid-century
- Peak-and-decline: Temperatures eventually stabilize/decline
- Rapid transition: Global emissions to net-zero by 2050
- Policy: Stringent climate policies (carbon pricing €200+/ton CO2)
- Technology: Rapid renewable energy cost decline, high electrification
- Market: Structural shifts in energy, transport, agriculture sectors
- IPCC equivalent: SSP1-2.6 (or RCP 2.6)

**2°C Pathway (Paris Agreement-Aligned)**
- Peak warming: ~2°C above pre-industrial
- Moderate transition: 50% emissions reduction by 2030, net-zero by 2070
- Policy: Moderate carbon pricing (€50-100/ton CO2)
- Technology: Slower cost curves, hybrid technology deployment
- Market: Moderate transition risks, emerging opportunities
- IPCC equivalent: SSP2-4.5 (or RCP 4.5)

**4°C+ Pathway (Business-As-Usual)**
- Peak warming: 4-5°C by 2100
- Delayed action: Limited climate policy, incremental technology deployment
- Physical risks: Acute (extreme weather) and chronic (temperature shifts) intensify
- Market: Stranded assets emerge, compounding liabilities
- IPCC equivalent: SSP5-8.5 (or RCP 8.5)

### Time Horizon Definitions

| Horizon | Duration | Purpose | Example Applications |
| --- | --- | --- | --- |
| **Near-term** | 0-1 year (entity-specific) | Operational planning | Budget planning, risk registers |
| **Medium-term** | 1-5 years | Strategic planning | Capex plans, business development |
| **Long-term** | 5+ years (typically to 2050) | Long-lived assets, net-zero alignment | Infrastructure, supply chain transformation |

### Quantitative Scenario Analysis Structure

```
For each scenario (1.5°C, 2°C, 4°C+):
  For each time horizon (near, medium, long):
    For each business segment:
      
      1. REVENUE MODELING
         Base revenue
         × (1 + demand shift under scenario)
         × (1 + price change from transition/physical risks)
         = Scenario revenue
      
      2. COST IMPACT MODELING
         Base COGS
         + (Input cost inflation from physical risks)
         + (Regulatory compliance costs - carbon pricing, adaptation)
         + (Stranded asset write-downs)
         = Scenario operating costs
      
      3. CAPEX REQUIREMENTS
         Base capex
         + (Technology transition capex - renewable energy, EVs, efficiency)
         + (Resilience/adaptation capex - flood protection, heat management)
         = Scenario capex
      
      4. NPV CALCULATION
         NPV = Σ [Free Cash Flow_t / (1 + r + Δr)^t]
         where:
           r = baseline discount rate (WACC)
           Δr = climate risk premium (2-5% depending on exposure)
           Free Cash Flow_t = (Revenue - Costs) under scenario
      
      5. SENSITIVITY ANALYSIS
         Test variables:
         - Carbon price range: €10-200/ton CO2
         - Technology cost curves: ±50% from base case
         - Demand elasticity: ±30% from base case
         - Transition timeline: 5-20 year windows
         - Physical impact severity: ±20% from base case
```

---

## TCFD REPORTING REQUIREMENTS SUMMARY

### Narrative Disclosures (Qualitative)
- Board governance statement
- Management role description
- Risk/opportunity identification and assessment
- Strategy integration narrative
- Scenario analysis narrative (organization-specific interpretation)
- Risk management process narrative
- Metric selection rationale

### Structured Disclosures (Quantitative)
- GHG emissions inventory (Scope 1, 2, ±3)
- Multi-year emissions trends
- Emissions intensity metrics
- Targets and progress tracking
- Key financial metrics by scenario
- Climate risk concentration data

### Assurance/Certification
- Recommended: Third-party verification of GHG emissions
- Increasingly becoming mandatory through regional regulations
- Methodologies: ISO 14064, GHG Protocol

### Filing Requirements
- **Where:** Mainstream financial reports (annual reports, 10-K)
- **When:** Annually, minimum
- **Format:** Integrated into risk/governance sections
- **Frequency of update:** Annual (minimum); more frequent if material changes

---

## TCFD COMPLIANCE TIMELINE

| Year | Status | Geography | Entities |
| --- | --- | --- | --- |
| 2024 | **Mandatory** | UK | Listed companies, large financial institutions |
| 2025 | **Mandatory** | EU (CSRD) | Large & listed companies |
| 2025 | **Mandatory** | SEC (US) | Public companies (phased) |
| 2026 | **Mandatory** | Global | Expanding to mid-market through regional rules |

---

# PART 2: REMAINING FRAMEWORKS (Research In Progress)

## EU TAXONOMY REGULATION
**Status:** Research in progress  
**Expected completion:** Next research phase  

**Preliminary scope:**
- Activity alignment calculation methodology
- DNSH (Do No Significant Harm) assessment criteria
- KPI calculations: % revenue/capex/opex aligned
- Physical climate risk assessment requirements
- Output templates for institutional disclosure

## SEC CLIMATE DISCLOSURE RULES
**Status:** Research in progress  
**Expected completion:** Next research phase  

**Preliminary scope:**
- Scope 1/2/3 GHG calculation boundaries
- Form 10-K required disclosure fields
- Materiality thresholds for financial impact
- Attestation/assurance requirements
- Transition risk quantification methodology

## BASEL III CLIMATE RISK ADD-ON
**Status:** Research in progress  
**Expected completion:** Next research phase  

**Preliminary scope:**
- Portfolio climate risk data requirements
- Transition risk capital charge calculations
- Physical risk capital charge calculations
- Stress testing scenarios for capital adequacy
- Default probability adjustments for climate exposure

## EU EBA/ECB CLIMATE RISK GUIDELINES
**Status:** Research in progress  
**Expected completion:** Next research phase  

**Preliminary scope:**
- Credit risk assessment incorporating climate
- Asset classification by climate exposure
- Loan origination climate risk criteria
- Governance requirements for financial institutions
- Reporting templates and frequency

## UK FCA CLIMATE DISCLOSURE RULES
**Status:** Research in progress  
**Expected completion:** Next research phase  

**Preliminary scope:**
- Double materiality assessment methodology
- Entity-level vs product-level requirements
- Specific KPIs for asset managers (£5B+ AUM)
- Reporting timeline and certification
- Assurance requirements

---

# PART 3: DATABASE DESIGN IMPLICATIONS

## Input Data Tables Required (Based on TCFD)

```sql
-- Bank Asset Data (input from banks)
bank_assets (
  asset_id,
  bank_id,
  asset_type (real_estate, infrastructure, loan, investment),
  location (latitude, longitude, region),
  value_eur,
  annual_revenue,
  sector,
  sub_segment,
  construction_year,
  energy_consumption,
  insurance_coverage
)

-- Climate Hazard Exposure
climate_hazard_exposure (
  asset_id,
  hazard_type (flood, heat, wildfire, drought),
  exposure_level (low, medium, high, critical),
  physical_risk_score,
  transition_risk_score,
  scenario (1.5c, 2c, 4c)
)

-- GHG Emissions Data
ghg_emissions (
  entity_id,
  year,
  scope_1_tco2e,
  scope_2_location_tco2e,
  scope_2_market_tco2e,
  scope_3_tco2e,
  calculation_methodology,
  assurance_level
)

-- Scenario Assumptions
scenario_assumptions (
  scenario_id,
  carbon_price_per_ton_eur,
  renewable_energy_cost_decline_pct,
  demand_shift_pct,
  policy_implementation_timeline
)

-- Financial Projections by Scenario
scenario_financial_projection (
  entity_id,
  scenario,
  time_horizon,
  projected_revenue_eur,
  projected_costs_eur,
  projected_capex_eur,
  npv_eur,
  discount_rate_pct
)
```

## Processing Logic Modules Required

1. **GHG Emissions Calculator**
   - Input: Energy bills, fuel consumption, activity data
   - Process: Scope 1, 2, 3 calculation per GHG Protocol
   - Output: Annual emissions inventory

2. **Climate Risk Scorer**
   - Input: Asset location, type, climate hazards
   - Process: Physical & transition risk assessment
   - Output: Risk score (0-100)

3. **Scenario Modeler**
   - Input: Business financials, climate assumptions, scenario pathway
   - Process: Financial projection under scenario
   - Output: Revenue/cost/capex impact, NPV by scenario

4. **Regulatory Report Generator**
   - Input: All above processed data
   - Process: Map to regulatory templates (TCFD, Taxonomy, SEC, Basel, etc.)
   - Output: Compliance reports in required format

---

## Output Templates Required

### TCFD Disclosure Tables
- GHG Emissions Summary (annual, multi-year)
- GHG Intensity & Targets
- Risk/Opportunity Assessment
- Scenario Analysis Results
- Climate Governance Statement

### EU Taxonomy Output
- Activity Alignment Metrics (% revenue/capex)
- DNSH Compliance Evidence
- Physical Risk Assessment

### SEC Reporting (Form 10-K)
- Scope 1, 2, 3 GHG emissions
- Climate risk financial impact
- Transition risk metrics
- Governance disclosure

### Basel III Output
- Portfolio climate risk scores
- Capital adequacy ratios (climate-adjusted)
- Stress test results

---

## Next Steps for Architecture Design

1. **Complete research** on 5 remaining frameworks (EU Taxonomy, SEC, Basel III, EBA/ECB, FCA)
2. **Consolidate** all input/processing/output requirements into single matrix
3. **Design database schema** to accommodate all regulatory inputs
4. **Build processing layer** with modules for each calculation type
5. **Create output template generators** for each regulatory format
6. **Design regulator module** for reporting to authorities + certification

---

**Document Version:** 1.0 (Phase 1 complete)  
**Last Updated:** 2026-01-XX  
**Research Status:** TCFD complete; EU Taxonomy, SEC, Basel III, EBA/ECB, FCA in progress
