# Bank Data Templates for Regulatory Reporting

## Overview

These CSV files are templates that you (as a bank user) can download, edit with your actual data, and upload back to generate regulatory reports.

---

## 📋 Files Included

### 1. **portfolio_assets.csv**
Your bank's asset portfolio with climate risk exposure.

**Columns to update:**
- `Asset_ID` - Unique identifier for the asset
- `Asset_Name` - Name of the asset/company
- `Asset_Type` - Type (Coal, Oil & Gas, Real Estate, etc.)
- `Sector` - Industry sector
- `Region` - Geographic location (EU country or region)
- `Exposure_EUR_M` - Your bank's exposure in EUR millions
- `Annual_Revenue_EUR_M` - Annual revenue of the asset
- `Climate_Risk_Score` - 0-100 (0=low risk, 100=high risk)
- `Materiality_Score` - 0-100 (for disclosure assessment)
- `Description` - Notes on the asset

**Example data:**
- Oil & Gas operations: €2,400M exposure
- Coal mining: €450M exposure
- Renewable energy: €320M exposure
- Real estate portfolio: €2,100M exposure

---

### 2. **ghg_emissions.csv**
Greenhouse gas emissions from your financed assets (Scope 1, 2, 3).

**Columns to update:**
- `Emission_ID` - Unique identifier
- `Asset_ID` - Link to asset in portfolio_assets.csv
- `Asset_Name` - Name for reference
- `Scope` - 1 (Direct), 2 (Purchased), or 3 (Financed)
- `Category` - Type of emission (e.g., "Coal Combustion", "Electricity")
- `Emissions_tCO2e` - Tonnes of CO2 equivalent
- `Year` - Data year (e.g., 2023)
- `Data_Quality` - High/Medium/Low
- `Verification_Status` - Verified/Third-Party/Estimated
- `Notes` - Additional context

**Data provided:**
- Scope 1: Direct operations (coal burning, flaring)
- Scope 2: Purchased electricity
- Scope 3: Financed emissions (customer use of products)

---

### 3. **climate_scenarios.csv**
Climate scenarios for financial impact analysis.

**Columns to update:**
- `Scenario_ID` - Unique identifier
- `Scenario_Name` - E.g., "1.5°C Paris Aligned"
- `Warming_Target_C` - Global warming target (1.5, 2.0, 4.0)
- `Probability_Percent` - Your assessment of likelihood (0-100)
- `Type` - Ambitious/Moderate/Baseline
- `Description` - Detailed scenario description
- `Policy_Stringency` - Very High/High/Medium/Low
- `Carbon_Price_EUR_per_tonne` - Expected carbon price
- `Renewable_Energy_Share_2050` - % renewable energy by 2050
- `Key_Assumptions` - Policy and economic assumptions

**Pre-loaded scenarios:**
- 1.5°C: Paris-aligned, rapid transition (35% probability)
- 2.0°C: Moderate action, delayed transition (40% probability)
- 4.0°C: Business-as-usual, minimal action (25% probability)

---

## 🔄 How to Use

### Step 1: Download Templates
```
Sidebar → Compliance → Data Ingestion
→ Download Template CSV Files
```

### Step 2: Edit with Your Data
Open each CSV file in Excel or Google Sheets:
- **portfolio_assets.csv** - Add your real assets and exposures
- **ghg_emissions.csv** - Add your emission data by scope
- **climate_scenarios.csv** - Adjust probabilities and assumptions

### Step 3: Upload to Platform
```
Sidebar → Compliance → Data Ingestion
→ Upload CSV Files
→ Select Modules (Scenario Impact, Gap Analysis, etc.)
→ Select Output Formats (PDF, Excel, Dashboard)
→ Execute Workflows
```

### Step 4: Download Reports
- **PDF Reports** - Professional regulatory disclosures
- **Excel Workbooks** - Detailed analysis with charts
- **JSON APIs** - Machine-readable data
- **Dashboard** - Interactive visualization

---

## 📊 Data Format Rules

### Portfolio Assets
- **Exposure_EUR_M**: Must be positive number
- **Climate_Risk_Score**: 0-100 scale
- **Materiality_Score**: 0-100 scale

### GHG Emissions
- **Emissions_tCO2e**: Tonnes CO2 equivalent
- **Scope**: Must be 1, 2, or 3
- **Year**: Format YYYY (e.g., 2023)

### Climate Scenarios
- **Probability_Percent**: 0-100, sum should ≈ 100%
- **Warming_Target_C**: 1.5, 2.0, 2.5, 3.0, or 4.0
- **Carbon_Price**: EUR per tonne (positive number)

---

## 🎯 Example Workflow

**Bank Portfolio:**
1. Coal mining exposure: €450M → Climate risk 92/100
2. Oil & Gas portfolio: €2,400M → Climate risk 88/100
3. Renewable energy: €600M → Climate risk 10/100

**Emissions:**
- Financed coal combustion: 680,000 tCO2e/year
- Oil/gas customer use: 1,250,000 tCO2e/year
- Renewable generation: ~4,000 tCO2e/year (embedded)

**Scenarios:**
- 1.5°C probability: 35% → Stranded assets risk: €450-800M
- 2.0°C probability: 40% → Stranded assets risk: €300-600M
- 4.0°C probability: 25% → Minimal transition risk

**Output:**
- ✓ TCFD disclosure report (PDF)
- ✓ EU Taxonomy alignment (PDF)
- ✓ Scenario impact analysis (Excel)
- ✓ Peer benchmarking (Dashboard)
- ✓ API endpoints (JSON)

---

## 📝 Notes

- **Confidentiality**: These files contain sensitive bank data. Store securely.
- **Data Quality**: Better data = better reports. Verify emissions accuracy.
- **Scenario Assumptions**: Adjust based on your bank's climate views.
- **Annual Updates**: Re-run workflows yearly as assets and emissions change.

---

## ❓ Need Help?

- **Download templates** at the Data Ingestion page
- **Edit in Excel/Sheets** - standard CSV format
- **Upload back** to the platform for processing
- **Get results** in multiple formats within seconds

---

**Questions?** Contact your regulatory reporting team or compliance officer.
