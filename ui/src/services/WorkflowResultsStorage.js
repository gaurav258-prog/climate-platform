/**
 * Workflow Results Storage
 * Manages persistence of workflow execution results to browser localStorage
 * Allows dashboard and other components to access latest execution results
 */

export class WorkflowResultsStorage {
  static STORAGE_KEY = 'regulatory_workflow_results'

  /**
   * Save workflow execution results
   */
  static saveResults(results) {
    try {
      const data = {
        ...results,
        timestamp: new Date().toISOString(),
        savedAt: Date.now()
      }
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(data))
      return true
    } catch (error) {
      console.error('Failed to save workflow results:', error)
      return false
    }
  }

  /**
   * Retrieve saved workflow results
   */
  static getResults() {
    try {
      const data = localStorage.getItem(this.STORAGE_KEY)
      return data ? JSON.parse(data) : null
    } catch (error) {
      console.error('Failed to retrieve workflow results:', error)
      return null
    }
  }

  /**
   * Clear saved results
   */
  static clearResults() {
    try {
      localStorage.removeItem(this.STORAGE_KEY)
      return true
    } catch (error) {
      console.error('Failed to clear workflow results:', error)
      return false
    }
  }

  /**
   * Check if results exist and are recent (within last hour)
   */
  static hasRecentResults() {
    const results = this.getResults()
    if (!results || !results.savedAt) return false

    const oneHourAgo = Date.now() - (60 * 60 * 1000)
    return results.savedAt > oneHourAgo
  }

  /**
   * Get specific data for dashboard visualization
   */
  static getDashboardData() {
    const results = this.getResults()
    if (!results) return null

    const pd = results.processedData
    const bd = results.bankData

    return {
      bank: {
        name: bd?.orgName || 'Your Bank',
        assets: bd?.assetCount || 0,
        totalExposure: bd?.totalAssets || 0
      },
      scenarios: pd?.scenarioImpact?.scenarios || {},
      compliance: pd?.complianceGap || {},
      materiality: pd?.riskMateriality?.summary || {},
      benchmarking: pd?.benchmarking || {},
      portfolioAggregation: pd?.portfolioAggregation || {},
      timestamp: results.timestamp
    }
  }

  /**
   * Calculate risk percentages for dashboard display
   */
  static calculateRiskMetrics() {
    const results = this.getResults()
    if (!results?.processedData?.riskMateriality) {
      return {
        physicalRisk: 45,
        transitionRisk: 68,
        regulatoryRisk: 54,
        reputationalRisk: 32
      }
    }

    const assets = results.processedData.riskMateriality.assets || []
    const physicalRisks = assets.filter(a => a.physicalRiskScore > 0).map(a => a.physicalRiskScore)
    const transitionRisks = assets.filter(a => a.transitionRiskScore > 0).map(a => a.transitionRiskScore)

    const avgPhysical = physicalRisks.length > 0
      ? Math.round(physicalRisks.reduce((a, b) => a + b) / physicalRisks.length)
      : 45

    const avgTransition = transitionRisks.length > 0
      ? Math.round(transitionRisks.reduce((a, b) => a + b) / transitionRisks.length)
      : 68

    return {
      physicalRisk: Math.min(100, avgPhysical),
      transitionRisk: Math.min(100, avgTransition),
      regulatoryRisk: results.processedData.complianceGap?.overallCompletenessPercent || 54,
      reputationalRisk: Math.max(10, 100 - (results.processedData.complianceGap?.emissionsCoveragePercent || 70))
    }
  }

  /**
   * Get compliance framework status
   */
  static getComplianceStatus() {
    const results = this.getResults()
    if (!results?.processedData?.complianceGap) {
      return {
        tcfd: { complete: 95, status: 'Complete' },
        taxonomy: { complete: 58, status: 'In Progress' },
        sec: { complete: 65, status: 'In Progress' }
      }
    }

    const gaps = results.processedData.complianceGap.gaps || []
    const tcfdGaps = gaps.filter(g => g.framework === 'TCFD')
    const taxonomyGaps = gaps.filter(g => g.framework === 'EU Taxonomy')
    const secGaps = gaps.filter(g => g.framework === 'SEC')

    const tcfdComplete = tcfdGaps.length > 0
      ? Math.round(tcfdGaps.reduce((sum, g) => sum + g.completeness, 0) / tcfdGaps.length)
      : 95

    const taxonomyComplete = taxonomyGaps.length > 0
      ? Math.round(taxonomyGaps.reduce((sum, g) => sum + g.completeness, 0) / taxonomyGaps.length)
      : 58

    const secComplete = secGaps.length > 0
      ? Math.round(secGaps.reduce((sum, g) => sum + g.completeness, 0) / secGaps.length)
      : 65

    return {
      tcfd: { complete: tcfdComplete, status: tcfdComplete >= 90 ? 'Complete' : 'In Progress' },
      taxonomy: { complete: taxonomyComplete, status: taxonomyComplete >= 80 ? 'Complete' : 'In Progress' },
      sec: { complete: secComplete, status: secComplete >= 80 ? 'Complete' : 'In Progress' }
    }
  }

  /**
   * Get portfolio risk by sector
   */
  static getPortfolioRiskBySector() {
    const results = this.getResults()
    if (!results?.processedData?.riskMateriality?.assets) {
      return [
        { sector: 'Oil & Gas', flood: 8, heat: 7, wildfire: 9, seismic: 4 },
        { sector: 'Real Estate', flood: 6, heat: 8, wildfire: 5, seismic: 6 },
        { sector: 'Agriculture', flood: 9, heat: 9, wildfire: 6, seismic: 3 },
        { sector: 'Manufacturing', flood: 4, heat: 5, wildfire: 3, seismic: 7 }
      ]
    }

    const assets = results.processedData.riskMateriality.assets
    const sectors = {}

    assets.forEach(asset => {
      const sector = asset.assetType || 'Other'
      if (!sectors[sector]) {
        sectors[sector] = {
          sector,
          physicalRisk: asset.physicalRiskScore || 0,
          transitionRisk: asset.transitionRiskScore || 0,
          count: 1
        }
      } else {
        sectors[sector].count++
        sectors[sector].physicalRisk = Math.round((sectors[sector].physicalRisk + (asset.physicalRiskScore || 0)) / 2)
        sectors[sector].transitionRisk = Math.round((sectors[sector].transitionRisk + (asset.transitionRiskScore || 0)) / 2)
      }
    })

    return Object.values(sectors).slice(0, 4)
  }

  /**
   * Get scenario comparison data
   */
  static getScenarioComparison() {
    const results = this.getResults()
    if (!results?.processedData?.scenarioImpact?.scenarios) {
      return null
    }

    return Object.entries(results.processedData.scenarioImpact.scenarios).map(([name, data]) => ({
      scenario: name,
      npv: data.npvEUR_M,
      revenueImpact: data.revenueImpactPercent,
      strandedAssets: data.strandedAssetsEUR_M,
      transitionRisk: data.transitionRisk,
      physicalRisk: data.physicalRisk
    }))
  }
}

export default WorkflowResultsStorage
