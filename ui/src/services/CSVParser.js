/**
 * TCFD-Compliant CSV Parser
 * Parses bank data CSVs with all regulatory required fields
 */

export class CSVParser {
  /**
   * Parse CSV text into array of objects
   */
  static parseCSV(text) {
    const lines = text.trim().split('\n')
    if (lines.length < 2) return []

    const headers = lines[0].split(',').map(h => h.trim().replace(/^["']|["']$/g, ''))
    const rows = []

    for (let i = 1; i < lines.length; i++) {
      if (!lines[i].trim()) continue

      // Handle quoted fields with commas
      const row = this.parseCSVLine(lines[i])
      const obj = {}

      headers.forEach((header, idx) => {
        obj[header] = row[idx] ? row[idx].trim() : ''
      })

      rows.push(obj)
    }

    return rows
  }

  /**
   * Parse a single CSV line respecting quoted fields
   */
  static parseCSVLine(line) {
    const result = []
    let current = ''
    let insideQuotes = false

    for (let i = 0; i < line.length; i++) {
      const char = line[i]

      if (char === '"') {
        insideQuotes = !insideQuotes
      } else if (char === ',' && !insideQuotes) {
        result.push(current.trim())
        current = ''
      } else {
        current += char
      }
    }

    result.push(current.trim())
    return result
  }

  /**
   * Parse Portfolio Assets CSV (TCFD-compliant format)
   */
  static parsePortfolioAssets(csvText) {
    const rows = this.parseCSV(csvText)
    return rows.map((row, idx) => ({
      // Basic fields
      id: row.Asset_ID || `ASSET_${idx + 1}`,
      name: row.Asset_Name || `Asset ${idx + 1}`,
      type: row.Asset_Type || 'Other',
      sector: row.Sector || 'Unknown',
      region: row.Region || 'EU',
      country: row.Country || 'Unknown',

      // Geographic specificity (for physical risk assessment)
      latitude: parseFloat(row.Latitude) || null,
      longitude: parseFloat(row.Longitude) || null,

      // Financial data
      exposure: parseFloat(row.Exposure_EUR_M) || 0,
      revenue: parseFloat(row.Annual_Revenue_EUR_M) || 0,

      // Physical risk assessment (TCFD requirement)
      physicalRiskType: row.Physical_Risk_Type || 'Unknown',
      physicalRisk: parseFloat(row.Physical_Risk_Score_0_100) || 0,

      // Transition risk assessment (TCFD requirement)
      transitionRisk: parseFloat(row.Transition_Risk_Score_0_100) || 0,

      // Capital expenditure (for resilience capex calculation)
      capex: parseFloat(row.Capital_Expenditure_2024_2030_EUR_M) || 0,

      // Supply chain & resilience
      supplyChainRisk: row.Supply_Chain_Risk_Level || 'Medium',
      insuranceCoverage: parseFloat(row.Insurance_Coverage_Percent) || 0,

      // Time horizon and materiality
      timeHorizon: row.Time_Horizon_Impact || 'Medium-term',
      materialityNotes: row.Materiality_Assessment_Notes || '',

      // Energy efficiency (for real estate/mortgages)
      energyIntensity: row.Energy_Consumption_kWh_m2 ? parseFloat(row.Energy_Consumption_kWh_m2) : null,
      energyBucket: this.getEnergyBucket(parseFloat(row.Energy_Consumption_kWh_m2) || null),

      // EU Taxonomy fields (for EU banks)
      taxonomyActivityCode: row.Taxonomy_Activity_Code || null,
      taxonomyEligible: row.Taxonomy_Eligible === 'Yes',
      taxonomyAligned: row.Taxonomy_Aligned === 'Yes',

      // Raw row for audit trail
      _raw: row
    }))
  }

  /**
   * Classify energy intensity into TCFD buckets
   */
  static getEnergyBucket(kwhPerM2) {
    if (kwhPerM2 === null || kwhPerM2 === undefined) return 'Unmeasured'
    if (kwhPerM2 <= 100) return '0-100 kWh/m²'
    if (kwhPerM2 <= 200) return '100-200 kWh/m²'
    if (kwhPerM2 <= 300) return '200-300 kWh/m²'
    if (kwhPerM2 <= 400) return '300-400 kWh/m²'
    if (kwhPerM2 <= 500) return '400-500 kWh/m²'
    return '>500 kWh/m²'
  }

  /**
   * Parse GHG Emissions CSV (TCFD-compliant format)
   */
  static parseGHGEmissions(csvText) {
    const rows = this.parseCSV(csvText)
    const emissions = rows.map((row, idx) => ({
      id: row.Emission_ID || `EMIT_${idx + 1}`,
      assetId: row.Asset_ID || 'UNKNOWN',
      assetName: row.Asset_Name || 'Unknown Asset',
      year: parseInt(row.Year) || 2023,
      scope: parseInt(row.Scope) || 1,
      category: row.Category || 'Operations',
      emissions: parseFloat(row.Emissions_tCO2e) || 0,

      // GHG Protocol compliance
      calculationMethodology: row.Calculation_Methodology || 'Unspecified',
      emissionFactorSource: row.Emission_Factor_Source || 'IPCC',
      dataQuality: row.Data_Quality || 'Medium',
      verificationStatus: row.Verification_Status || 'Estimated',
      notes: row.Notes || '',

      // Raw row for audit trail
      _raw: row
    }))

    return emissions
  }

  /**
   * Parse Climate Scenarios CSV (TCFD-compliant format)
   */
  static parseClimateScenarios(csvText) {
    const rows = this.parseCSV(csvText)
    return rows.map((row, idx) => ({
      id: row.Scenario_ID || `SCEN_${idx + 1}`,
      name: row.Scenario_Name || `Scenario ${idx + 1}`,
      warming: parseFloat(row.Warming_Target_C) || 2.0,
      probability: parseFloat(row.Probability_Percent) / 100 || 0.33,
      type: row.Scenario_Type || 'Moderate',
      description: row.Description || '',

      // Time horizon
      timeHorizon: parseInt(row.Time_Horizon_Years) || 2050,

      // Carbon pricing trajectory (TCFD requirement)
      carbonPrice_2025: parseFloat(row.Carbon_Price_EUR_per_tonne_2025) || 50,
      carbonPrice_2030: parseFloat(row.Carbon_Price_EUR_per_tonne_2030) || 100,
      carbonPrice_2050: parseFloat(row.Carbon_Price_EUR_per_tonne_2050) || 200,

      // Renewable energy share evolution (TCFD requirement)
      renewableShare_2025: parseFloat(row.Renewable_Energy_Share_2025_Percent) || 25,
      renewableShare_2050: parseFloat(row.Renewable_Energy_Share_2050_Percent) || 80,

      // Technology and price assumptions
      oilPrice_2030: parseFloat(row.Oil_Price_USD_per_barrel_2030) || 70,
      gasPrice_2030: parseFloat(row.Gas_Price_USD_per_MMBTU_2030) || 8,
      techCostReduction: parseFloat(row.Technology_Cost_Reduction_PERCENT_2030) || 30,

      // Policy context
      policyStringency: row.Policy_Stringency || 'Medium',
      keyAssumptions: row.Key_Assumptions || '',

      // Financial impact template
      revenueImpact: parseFloat(row.Revenue_Impact_Transition_Percent) || 0,
      capexRequirement: parseFloat(row.Capex_Requirement_Addition_Percent) || 0,

      // Raw row for audit trail
      _raw: row
    }))
  }

  /**
   * Validate portfolio data for required TCFD fields
   */
  static validatePortfolio(assets) {
    const issues = []

    if (!assets || assets.length === 0) {
      issues.push('No portfolio assets provided')
      return issues
    }

    assets.forEach((asset, idx) => {
      if (!asset.id) issues.push(`Asset ${idx}: Missing Asset_ID`)
      if (!asset.name) issues.push(`Asset ${idx}: Missing Asset_Name`)
      if (!asset.type) issues.push(`Asset ${idx}: Missing Asset_Type`)
      if (asset.exposure === null || asset.exposure === undefined) {
        issues.push(`Asset ${idx}: Missing Exposure_EUR_M`)
      }
      if (asset.revenue === null || asset.revenue === undefined) {
        issues.push(`Asset ${idx}: Missing Annual_Revenue_EUR_M`)
      }
      // Physical risk assessment is optional but recommended
      if (asset.physicalRisk === null || asset.physicalRisk === undefined) {
        console.warn(`Asset ${idx}: Physical risk not specified (recommended)`)
      }
    })

    return issues
  }

  /**
   * Validate emissions data for required TCFD fields
   */
  static validateEmissions(emissions) {
    const issues = []

    if (!emissions || emissions.length === 0) {
      issues.push('No emissions data provided')
      return issues
    }

    const scopes = {}
    emissions.forEach((e, idx) => {
      if (!e.scope) issues.push(`Emission ${idx}: Missing Scope (1, 2, or 3)`)
      if (e.emissions === null || e.emissions === undefined) {
        issues.push(`Emission ${idx}: Missing Emissions_tCO2e`)
      }

      // Track scope coverage
      scopes[e.scope] = (scopes[e.scope] || 0) + e.emissions
    })

    // Check Scope 1 & 2 coverage (mandatory)
    if (!scopes[1] && !scopes[2]) {
      issues.push('Missing Scope 1 or 2 emissions (mandatory for TCFD disclosure)')
    }

    return issues
  }

  /**
   * Validate scenarios for required TCFD fields
   */
  static validateScenarios(scenarios) {
    const issues = []

    if (!scenarios || scenarios.length === 0) {
      issues.push('No scenarios provided')
      return issues
    }

    // Check for required scenario types
    const warmingTargets = scenarios.map(s => s.warming)
    if (!warmingTargets.includes(1.5) && !warmingTargets.includes(2.0)) {
      issues.push('Missing 1.5°C or 2°C scenario (required for TCFD)')
    }

    // Check probabilities sum to ~100%
    const totalProb = scenarios.reduce((sum, s) => sum + (s.probability || 0), 0)
    if (totalProb < 0.95 || totalProb > 1.05) {
      issues.push(`Scenario probabilities sum to ${(totalProb * 100).toFixed(0)}% (should be ~100%)`)
    }

    return issues
  }

  /**
   * Validate all data together
   */
  static validateAll(portfolio, emissions, scenarios) {
    const issues = [
      ...this.validatePortfolio(portfolio),
      ...this.validateEmissions(emissions),
      ...this.validateScenarios(scenarios)
    ]

    return {
      valid: issues.length === 0,
      issues,
      warnings: []
    }
  }
}

export default CSVParser
