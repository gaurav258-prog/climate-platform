# REGULATORY REQUIREMENTS MATRIX FOR REGTECH PLATFORM
## Input Data → Processing Logic → Output Format

---

## 1. TCFD RECOMMENDATIONS (Global Baseline)

### INPUT DATA REQUIRED
**From Banks/Financial Institutions:**
- [ ] Asset inventory by segment (geography, sector, asset type)
- [ ] Revenue & asset value breakdown by business line
- [ ] Operating expenses and capital expenditure by location
- [ ] Supply chain dependencies and vulnerability mappings
- [ ] Physical asset locations (latitude/longitude for hazard exposure)
- [ ] GHG emissions (Scope 1, 2, 3 if available)
- [ ] Current insurance/hedging positions
- [ ] Strategic plans and capital allocation decisions

**Climate Data Inputs:**
- [ ] Geographic climate hazard data (flood, heat, drought, wildfire risk by location)
- [ ] Scenario climate pathways (1.5°C, 2°C, >3°C)
- [ ] Carbon pricing trajectories (€10-200/ton CO2)
- [ ] Technology cost curves (renewable energy, batteries, etc.)

### PROCESSING LOGIC REQUIRED
1. **Scenario Modeling**
   - Model cash flows under 3 climate pathways (1.5°C, 2°C, >3°C)
   - Time horizons: 0-1yr (short), 1-5yr (medium), 5+ yr (long)
   - Input variables: carbon prices, technology costs, demand shifts

2. **Financial Quantification**
   - NPV calculation: CF_t / (1 + r + climate_risk_premium)^t
   - Climate risk premium: 2-5% depending on sector exposure
   - Stranded asset identification (especially for fossil fuel assets)
   - Revenue impact modeling (market demand shifts under scenarios)
   - Cost impact modeling (input costs, regulatory compliance, adaptation)
   - Capex requirement assessment (resilience investments)

3. **Stress Testing**
   - Value-at-Risk (VaR) calculation for portfolio under scenarios
   - Impact channels: asset damage, operational disruption, demand shifts, policy shocks
   - Sensitivity analysis on key variables (carbon price ±50%, temp ±1°C, demand ±20%)

4. **Risk Scoring**
   - Quantify exposure (% of portfolio in climate-vulnerable areas/sectors)
   - Quantify sensitivity (financial impact per unit of climate variable)
   - Quantify adaptive capacity (% mitigation through strategy)
   - Overall risk score per scenario

### OUTPUT FORMAT REQUIRED
- **Narrative Disclosure** (PDF/Word)
  - Governance statement (board oversight, risk management)
  - Strategy narrative (how climate risks inform strategy)
  - Risk management process description
  
- **Quantitative Tables** (Excel/PDF)
  - Financial impacts by scenario (% revenue/cost/capex change)
  - Time-horizon specific projections
  - Key metrics: 1.5°C NPV vs 2°C NPV vs BAU NPV
  
- **Supplementary Data** (Spreadsheet)
  - Assumptions (discount rate, carbon price path, technology costs)
  - Sensitivity analysis results
  - Confidence intervals

### TIMELINE/COMPLIANCE
- **Effective Date:** Voluntary now; increasingly mandatory
- **EU/UK:** Mandatory for listed companies, large financial institutions (2024-2025)
- **SEC:** Final rule effective 2024, phased implementation 2025-2026
- **Reporting Frequency:** Annual

---

## 2. EU TAXONOMY REGULATION (EUROPE PRIORITY)

**[RESEARCH IN PROGRESS - Key Questions]**

### INPUT DATA REQUIRED
- [ ] Classification of economic activities (Taxonomy codes)
- [ ] Revenue/capex/opex breakdown by Taxonomy activity
- [ ] DNSH (Do No Significant Harm) assessment evidence
- [ ] Physical risk indicators for climate-relevant activities
- [ ] Transition risk indicators (carbon intensity trends, etc.)

### PROCESSING LOGIC REQUIRED
- [ ] Activity alignment calculation (% revenue/capex aligned with EU Taxonomy)
- [ ] DNSH compliance verification (against specific environmental thresholds)
- [ ] Physical risk assessment (flood, heat, drought impact on activity viability)
- [ ] Transitional activity identification (fossil fuel with phase-out)

### OUTPUT FORMAT REQUIRED
- [ ] KPI metrics: % revenue aligned, % capex aligned, % opex aligned
- [ ] DNSH compliance evidence documentation
- [ ] Physical risk assessment by activity
- [ ] Discrepancy report (activities failing DNSH criteria)

### TIMELINE/COMPLIANCE
- [ ] TBD (researching)

---

## 3. SEC CLIMATE DISCLOSURE RULES (US - IMPACTS EUROPEAN SUBSIDIARIES)

**[RESEARCH IN PROGRESS - Key Questions]**

### INPUT DATA REQUIRED
- [ ] Scope 1 GHG emissions (direct company operations)
- [ ] Scope 2 GHG emissions (purchased electricity/heat)
- [ ] Scope 3 GHG emissions (value chain - if material)
- [ ] Climate risk impact quantification (material risks to business)
- [ ] Climate governance structure
- [ ] Risk management processes

### PROCESSING LOGIC REQUIRED
- [ ] GHG emissions calculation per methodologies (GHG Protocol, EPA, etc.)
- [ ] Materiality assessment (>5% earnings impact threshold)
- [ ] Climate risk financial quantification
- [ ] Scenario analysis under SEC-required pathways

### OUTPUT FORMAT REQUIRED
- [ ] SEC Form 10-K climate risk disclosure section
- [ ] GHG inventory (Scope 1, 2, ±3)
- [ ] Climate risk impact quantification tables
- [ ] Attestation/assurance statement

### TIMELINE/COMPLIANCE
- [ ] TBD (researching)

---

## 4. BASEL III CLIMATE RISK ADD-ON (BANKING)

**[RESEARCH IN PROGRESS - Key Questions]**

### INPUT DATA REQUIRED
- [ ] Bank portfolio data by asset class (loans, investments)
- [ ] Borrower/counterparty climate risk exposure
- [ ] Collateral physical risk assessment
- [ ] Transition risk indicators (carbon intensity, sector exposure)
- [ ] Default probability data

### PROCESSING LOGIC REQUIRED
- [ ] Climate risk data requirements (physical/transition scoring)
- [ ] Risk weight adjustments for climate exposure
- [ ] Stress testing scenarios (transition risk, physical risk shocks)
- [ ] Capital adequacy impact calculation
- [ ] Default probability adjustments

### OUTPUT FORMAT REQUIRED
- [ ] Regulatory capital calculation (risk-weighted assets adjusted for climate)
- [ ] Stress test results
- [ ] Governance attestation
- [ ] Portfolio climate risk summary

### TIMELINE/COMPLIANCE
- [ ] TBD (researching)

---

## 5. EU EBA/ECB CLIMATE RISK GUIDELINES (EUROPEAN BANKS)

**[RESEARCH IN PROGRESS - Key Questions]**

### INPUT DATA REQUIRED
- [ ] Bank credit portfolio exposure by sector/geography
- [ ] Borrower climate risk assessments
- [ ] Collateral physical risk by location
- [ ] Governance documentation (climate risk oversight)
- [ ] Stress test inputs

### PROCESSING LOGIC REQUIRED
- [ ] Credit risk assessment incorporating climate
- [ ] Asset classification by climate exposure
- [ ] Loan origination climate risk scoring
- [ ] Portfolio concentration risk (climate-vulnerable sectors)
- [ ] Stress testing under EBA/ECB scenarios

### OUTPUT FORMAT REQUIRED
- [ ] Climate risk management policy
- [ ] Portfolio climate risk assessment
- [ ] Governance attestation
- [ ] Stress test results

### TIMELINE/COMPLIANCE
- [ ] TBD (researching)

---

## 6. UK FCA CLIMATE DISCLOSURE REQUIREMENTS

**[RESEARCH IN PROGRESS - Key Questions]**

### INPUT DATA REQUIRED
- [ ] Double materiality assessment (financial & impact materiality)
- [ ] Board-level climate governance documentation
- [ ] Climate risk integration into strategy
- [ ] Transition plan details

### PROCESSING LOGIC REQUIRED
- [ ] Materiality assessment (both dimensions)
- [ ] Climate risk scenario analysis
- [ ] Governance compliance verification

### OUTPUT FORMAT REQUIRED
- [ ] Listed company climate disclosure report
- [ ] Transition plan documentation
- [ ] Governance attestation

### TIMELINE/COMPLIANCE
- [ ] TBD (researching)

---

## SYNTHESIS QUESTIONS FOR REGTECH ARCHITECTURE

Based on preliminary TCFD research, what we need to finalize for database design:

### For ALL Regulations:
1. **Exact Input Data Fields** - What specific data types/formats?
   - What GIS format for asset locations?
   - What taxonomy codes/classification systems?
   - What standard units (EUR, tonnes, MWh)?

2. **Processing Methodologies** - Any standardized calculation formulas?
   - Are there approved/mandatory climate models?
   - What discount rates are standard?
   - What carbon price trajectories are regulatory standard?

3. **Output Certification** - Who certifies/verifies outputs?
   - Third-party auditor required?
   - Regulatory pre-approval needed?
   - Self-certification acceptable?

4. **Integration Points** - How do these regulations overlap?
   - Does TCFD feed into Taxonomy compliance?
   - Does SEC data satisfy EU requirements?
   - Are there conflicts?

5. **Penalties/Enforcement** - What happens if non-compliant?
   - Financial penalties?
   - Regulatory restrictions?
   - Market impact?

---

**STATUS:** Research 5/6 frameworks in progress. TCFD framework fully extracted and mapped.

**NEXT STEP:** Complete research on EU Taxonomy, SEC Rules, Basel III, EBA/ECB, FCA guidelines with same input→processing→output format.
