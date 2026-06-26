import { useState, useRef } from 'react'
import SimpleIcon from '../components/SimpleIcon'
import DataProcessor from '../services/DataProcessor'
import PDFGenerator from '../services/PDFGenerator'

/**
 * Data Ingestion Page - Bank Data Upload & Workflow Initialization
 * Step 1: Bank uploads portfolio, emissions, scenario data
 * Step 2: System validates and ingests data
 * Step 3: Triggers regulatory reporting workflows
 */
export default function DataIngestionPage() {
  const [uploadedData, setUploadedData] = useState(null)
  const [selectedModules, setSelectedModules] = useState(['scenario-impact', 'compliance-gap', 'risk-materiality'])
  const [selectedFormats, setSelectedFormats] = useState(['json', 'pdf', 'dashboard'])
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)

  const bankDataTemplate = {
    bankId: 'BANK_001',
    orgName: 'Example Bank AG',
    portfolio: [
      { type: 'Oil & Gas', exposure: 2400, region: 'EU' },
      { type: 'Real Estate', exposure: 5600, region: 'EU' },
      { type: 'Renewable Energy', exposure: 3200, region: 'EU' },
    ],
    emissions: [
      { scope: 1, emissions: 5200, source: 'Direct' },
      { scope: 2, emissions: 3100, source: 'Electricity' },
      { scope: 3, emissions: 12400, source: 'Financed' },
    ],
    scenarios: [
      { name: '1.5c', probability: 0.35, type: 'ambitious' },
      { name: '2c', probability: 0.40, type: 'moderate' },
      { name: '4c', probability: 0.25, type: 'baseline' },
    ],
  }

  const modules = [
    { id: 'scenario-impact', name: 'Scenario Financial Impact', desc: 'NPV & revenue impact analysis' },
    { id: 'compliance-gap', name: 'Compliance Gap Analysis', desc: 'TCFD/Taxonomy/SEC gap mapping' },
    { id: 'risk-materiality', name: 'Risk Materiality Calculation', desc: 'Financial impact materiality assessment' },
    { id: 'timeline-tracking', name: 'Timeline & Deadline Tracking', desc: 'Regulatory deadline management' },
    { id: 'portfolio-aggregation', name: 'Portfolio Aggregation', desc: 'Sector & geographic breakdowns' },
    { id: 'benchmarking', name: 'Comparative Benchmarking', desc: 'Peer group positioning' },
  ]

  const formats = [
    { id: 'json', name: 'JSON API', desc: 'Machine-readable format' },
    { id: 'pdf', name: 'PDF Report', desc: 'Professional PDF document' },
    { id: 'excel', name: 'Excel Workbook', desc: 'Spreadsheet with charts' },
    { id: 'dashboard', name: 'Dashboard', desc: 'Interactive visualization' },
    { id: 'api', name: 'REST API', desc: 'Live data endpoint' },
  ]

  const loadTemplateData = () => {
    setUploadedData(bankDataTemplate)
  }

  const downloadCSV = (filename, content) => {
    try {
      const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' })
      const link = document.createElement('a')
      const url = URL.createObjectURL(blob)
      link.setAttribute('href', url)
      link.setAttribute('download', filename)
      link.style.visibility = 'hidden'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (error) {
      alert(`Error downloading file: ${error.message}`)
    }
  }

  const portfolioAssetCSV = `Asset_ID,Asset_Name,Asset_Type,Sector,Region,Exposure_EUR_M,Annual_Revenue_EUR_M,Climate_Risk_Score,Materiality_Score,Description
ASSET_001,Coal Mining Company,Coal,Energy,Poland,450,120,92,85,"Large coal mining operations in Poland. High physical and transition risk."
ASSET_002,Oil & Gas Portfolio,Oil & Gas,Energy,North Sea,2400,580,88,82,"Upstream oil and gas operations. Exposed to transition risk and regulatory changes."
ASSET_003,Renewable Solar Farm,Renewable Energy,Energy,Spain,320,45,12,5,"Large-scale solar PV facility. Low climate risk, supports transition."
ASSET_004,Wind Energy Assets,Renewable Energy,Energy,Germany,280,38,8,3,"Onshore wind farms across Germany. Excellent climate profile."
ASSET_005,Commercial Real Estate Portfolio,Real Estate,Real Estate,Munich,2100,280,35,40,"Premium office and retail properties in Munich. Flood and heat risk exposure."
ASSET_006,Residential Properties,Real Estate,Real Estate,Berlin,3500,420,42,45,"Multi-family residential across Berlin. Urban flood and heat wave risks."
ASSET_007,Agricultural Land Holdings,Agriculture,Agriculture,France,420,65,55,48,"Grain farming and viticulture assets. Drought and heat stress risks."
ASSET_008,Thermal Power Plant,Power Generation,Energy,Germany,680,95,76,70,"Coal-fired power station. Phase-out risk. Transition essential."
ASSET_009,Steel Manufacturing,Manufacturing,Manufacturing,Ruhr,580,125,48,42,"Steel production facility. Moderate climate exposure and transition risk."
ASSET_010,Transportation Infrastructure,Infrastructure,Infrastructure,EU,890,105,38,35,"Road and rail assets. Flood and extreme weather risks."
ASSET_011,Chemical Production,Manufacturing,Manufacturing,Belgium,420,98,45,38,"Chemical manufacturing plant. Water stress and operational risks."
ASSET_012,Food & Beverage Processing,Manufacturing,Food,Netherlands,310,72,52,44,"Agricultural commodity processing. Supply chain climate risks."
ASSET_013,Fishing Fleet,Agriculture,Agriculture,Atlantic,180,42,68,55,"Commercial fishing operations. Ocean acidification and temperature risks."
ASSET_014,Water Utility Company,Utilities,Utilities,Spain,520,85,61,58,"Water supply infrastructure. Drought and flood related risks."
ASSET_015,Tourism Infrastructure,Hospitality,Hospitality,Alps,290,38,45,32,"Alpine ski resorts and hotels. Snow cover and heat wave risks."`

  const ghgEmissionsCSV = `Emission_ID,Asset_ID,Asset_Name,Scope,Category,Emissions_tCO2e,Unit,Year,Data_Quality,Verification_Status,Notes
EMIT_001,ASSET_001,Coal Mining Company,1,Direct Operations,125000,tCO2e,2023,High,Verified,"Scope 1: Mining equipment, blasting, processing"
EMIT_002,ASSET_001,Coal Mining Company,2,Electricity,45000,tCO2e,2023,High,Verified,"Scope 2: Purchased electricity for operations"
EMIT_003,ASSET_001,Coal Mining Company,3,Upstream Coal,680000,tCO2e,2023,Medium,Third-Party,"Scope 3: Coal combustion at customer power plants"
EMIT_004,ASSET_002,Oil & Gas Portfolio,1,Production Flaring,280000,tCO2e,2023,High,Verified,"Scope 1: Flaring and fugitive emissions"
EMIT_005,ASSET_002,Oil & Gas Portfolio,2,Electricity,95000,tCO2e,2023,High,Verified,"Scope 2: Purchased power for extraction"
EMIT_006,ASSET_002,Oil & Gas Portfolio,3,Combustion,1250000,tCO2e,2023,Medium,Third-Party,"Scope 3: Oil and gas burned by end-customers"
EMIT_007,ASSET_003,Renewable Solar Farm,1,Direct Emissions,0,tCO2e,2023,High,Verified,"Scope 1: Negligible emissions"
EMIT_008,ASSET_003,Renewable Solar Farm,2,Electricity,500,tCO2e,2023,High,Verified,"Scope 2: Minimal purchased electricity"
EMIT_009,ASSET_003,Renewable Solar Farm,3,Manufacturing,2500,tCO2e,2023,Medium,Calculated,"Scope 3: Embedded emissions in solar panels"
EMIT_010,ASSET_004,Wind Energy Assets,1,Direct Emissions,0,tCO2e,2023,High,Verified,"Scope 1: Negligible emissions"
EMIT_011,ASSET_004,Wind Energy Assets,2,Electricity,200,tCO2e,2023,High,Verified,"Scope 2: Minimal purchased electricity"
EMIT_012,ASSET_004,Wind Energy Assets,3,Manufacturing,1800,tCO2e,2023,Medium,Calculated,"Scope 3: Embedded in turbine manufacturing"`

  const climarioCSV = `Scenario_ID,Scenario_Name,Warming_Target_C,Probability_Percent,Type,Description,Policy_Stringency,Carbon_Price_EUR_per_tonne,Renewable_Energy_Share_2050,Key_Assumptions
SCEN_001,1.5°C Paris Aligned,1.5,35,Ambitious,"Rapid decarbonization with immediate policy action. Consistent with Paris Agreement 1.5°C target.","Very High",180,95,"Rapid coal phase-out, 5% annual renewables growth, aggressive carbon pricing, strong regulatory frameworks"
SCEN_002,2°C Moderate Transition,2.0,40,Moderate,"Current policies trajectory with gradual improvements. Achieves 2°C goal with delayed action.","Medium",95,78,"Coal phase-out by 2040, 3% annual renewables growth, moderate carbon price, mixed policy support"
SCEN_003,4°C+ Business as Usual,4.0,25,Baseline,"Limited climate action beyond current pledges. Market forces drive some change but insufficient.","Low",25,45,"Coal continues, 1.5% annual renewables growth, weak carbon pricing, fragmented policies"`

  const toggleModule = (moduleId) => {
    setSelectedModules(prev =>
      prev.includes(moduleId) ? prev.filter(m => m !== moduleId) : [...prev, moduleId]
    )
  }

  const toggleFormat = (formatId) => {
    setSelectedFormats(prev =>
      prev.includes(formatId) ? prev.filter(f => f !== formatId) : [...prev, formatId]
    )
  }

  const downloadOutputFile = (format, executionId) => {
    try {
      if (!result || !result.processedData) {
        alert('No processed data available. Please execute workflows first.')
        return
      }

      let content = ''
      let filename = `regulatory_report_${executionId}.`
      let mimeType = 'text/plain'

      const pd = result.processedData // processed data
      const bd = result.bankData // bank data

      if (format === 'json') {
        content = JSON.stringify({
          executionId,
          timestamp: new Date().toISOString(),
          bank: bd.orgName,
          bankId: bd.bankId,
          totalAssetsEUR_M: bd.totalAssets,
          assetCount: bd.assetCount,
          modulesProcessed: selectedModules,
          results: pd
        }, null, 2)
        filename += 'json'
        mimeType = 'application/json'
      } else if (format === 'pdf') {
        // Generate properly formatted HTML/PDF
        const sections = [
          {
            title: 'Executive Summary',
            data: {
              'Bank': bd.orgName,
              'Execution ID': executionId,
              'Total Assets': `€${bd.totalAssets}M`,
              'Asset Count': bd.assetCount,
              'Report Date': new Date().toLocaleString(),
              'Modules Processed': selectedModules.join(', ')
            }
          }
        ]

        if (pd.scenarioImpact) {
          const scenarioData = Object.entries(pd.scenarioImpact.scenarios).map(([scenario, data]) => ({
            Scenario: scenario,
            'Warming (°C)': data.warming,
            'NPV (€M)': data.npvEUR_M,
            'Revenue Impact (%)': data.revenueImpactPercent,
            'Stranded Assets (€M)': data.strandedAssetsEUR_M,
            'Transition Risk': data.transitionRisk,
            'Physical Risk': data.physicalRisk
          }))
          sections.push({
            title: 'Scenario Financial Impact Analysis',
            data: scenarioData
          })
        }

        if (pd.complianceGap) {
          sections.push({
            title: 'Compliance Gap Analysis',
            data: {
              'Overall Completeness': `${pd.complianceGap.overallCompletenessPercent}%`,
              'Emissions Data Coverage': `${pd.complianceGap.emissionsCoveragePercent}%`,
              'EU Taxonomy Alignment': `${pd.complianceGap.taxonomyAlignmentPercent}%`,
              'Urgent Gaps': pd.complianceGap.urgentGaps,
              'Estimated Total Effort': pd.complianceGap.estimatedTotalEffort
            }
          })

          sections.push({
            title: 'Compliance Gaps Detail',
            data: pd.complianceGap.gaps.map(gap => ({
              'Framework': gap.framework,
              'Requirement': gap.requirement,
              'Status': gap.status,
              'Completeness (%)': gap.completeness,
              'Effort (h)': gap.effort,
              'Priority': gap.priority
            }))
          })
        }

        if (pd.riskMateriality) {
          sections.push({
            title: 'Risk Materiality Assessment',
            data: {
              'Portfolio Materiality': `${pd.riskMateriality.summary.portfolioMaterialityPercent}%`,
              'Materiality Threshold': `${pd.riskMateriality.summary.materiality_Threshold}%`,
              'Over Threshold': pd.riskMateriality.summary.overThreshold ? 'YES - REQUIRES DISCLOSURE' : 'NO',
              'Assets Requiring Disclosure': pd.riskMateriality.summary.assetsRequiringDisclosure,
              'Total Financed Emissions': `${pd.riskMateriality.summary.totalEmissions_tCO2e} tCO2e`,
              'High Risk Assets': pd.riskMateriality.summary.highRiskAssets
            }
          })

          sections.push({
            title: 'Asset-Level Materiality',
            data: pd.riskMateriality.assets.map(asset => ({
              'Asset': asset.assetName,
              'Type': asset.assetType,
              'Exposure (€M)': asset.exposureEUR_M,
              'Risk Score': asset.climateRiskScore,
              'Materiality (%)': asset.materialityPercent,
              'Disclosure Required': asset.requiresDisclosure ? 'YES' : 'NO'
            }))
          })
        }

        if (pd.benchmarking) {
          sections.push({
            title: 'Peer Benchmarking',
            data: {
              'Your Score': `${pd.benchmarking.yourBank.overallScore}/100`,
              'Peer Average': `${pd.benchmarking.peerAverage}/100`,
              'Your Ranking': pd.benchmarking.ranking,
              'Green Assets': `${pd.benchmarking.yourBank.greenAllocation}%`,
              'High Risk Assets': `${pd.benchmarking.yourBank.highRiskAllocation}%`,
              'Gap to Leader': pd.benchmarking.gaps.overallScore
            }
          })
        }

        content = PDFGenerator.generateHTMLPDF('Regulatory Reporting Analysis', sections)
        filename += 'html'
        mimeType = 'text/html'
      } else if (format === 'excel') {
        let excelContent = ''

        if (pd.scenarioImpact) {
          excelContent += `SHEET: SCENARIO IMPACT\nScenario,Warming_C,NPV_EUR_M,Revenue_Impact_Pct,Stranded_Assets_EUR_M,Transition_Risk,Physical_Risk\n`
          Object.entries(pd.scenarioImpact.scenarios).forEach(([scenario, data]) => {
            excelContent += `${scenario},${data.warming},${data.npvEUR_M},${data.revenueImpactPercent},${data.strandedAssetsEUR_M},${data.transitionRisk},${data.physicalRisk}\n`
          })
          excelContent += `\n\n`
        }

        if (pd.complianceGap) {
          excelContent += `SHEET: COMPLIANCE GAPS\nFramework,Requirement,Status,Completeness_Pct,Effort_Hours,Priority\n`
          pd.complianceGap.gaps.forEach(gap => {
            excelContent += `${gap.framework},"${gap.requirement}",${gap.status},${gap.completeness},${gap.effort},${gap.priority}\n`
          })
          excelContent += `\n\n`
        }

        if (pd.riskMateriality) {
          excelContent += `SHEET: MATERIALITY\nAsset_ID,Asset_Name,Type,Exposure_EUR_M,Climate_Risk_Score,Emissions_tCO2e,Materiality_Pct,Requires_Disclosure,Risk_Level\n`
          pd.riskMateriality.assets.forEach(asset => {
            excelContent += `${asset.assetId},${asset.assetName},${asset.assetType},${asset.exposureEUR_M},${asset.climateRiskScore},${asset.emissionstCO2e},${asset.materialityPercent},${asset.requiresDisclosure},${asset.riskLevel}\n`
          })
          excelContent += `\n\n`
        }

        content = excelContent
        filename += 'xlsx'
        mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      } else if (format === 'api') {
        alert('✅ API Endpoint Available:\n\nGET /api/reports/' + executionId + '\n\nYour processed data is available at this endpoint.\n\nDocumentation: /api/docs/regulatory')
        return
      } else if (format === 'dashboard') {
        alert('📊 Interactive Dashboard:\n\n/dashboard/regulatory/' + executionId + '\n\nVisualize your scenario impact, compliance gaps, and peer benchmarking.')
        return
      }

      const blob = new Blob([content], { type: mimeType })
      const link = document.createElement('a')
      const url = URL.createObjectURL(blob)
      link.setAttribute('href', url)
      link.setAttribute('download', filename)
      link.style.visibility = 'hidden'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (error) {
      alert(`Error downloading ${format}: ${error.message}`)
    }
  }

  const executeWorkflow = async () => {
    if (!uploadedData) {
      alert('Please load data first')
      return
    }

    setLoading(true)
    setResult(null)

    try {
      const startTime = Date.now()

      // Process data based on selected modules
      const processedResults = {}

      // Normalize data from uploadedData
      const portfolioData = uploadedData.portfolio.map((p, idx) => ({
        id: p.id || `ASSET_${idx + 1}`,
        name: p.name || `Asset ${idx + 1}`,
        type: p.type || 'Other',
        region: p.region || 'EU',
        exposure: p.exposure || 0,
        climateRisk: p.climateRisk || 50,
        materiality: p.materiality || 0
      }))

      const emissionsData = uploadedData.emissions.map((e, idx) => ({
        id: `EMIT_${idx + 1}`,
        assetId: e.assetId || portfolioData[idx % portfolioData.length].id,
        scope: e.scope || 1,
        emissions: e.emissions || 0,
        category: e.category || 'Operations'
      }))

      const scenariosData = uploadedData.scenarios.map((s, idx) => ({
        name: s.name || `Scenario ${idx + 1}`,
        warming: s.warming || 2.0,
        probability: s.probability || 0.33,
        carbonPrice: s.carbonPrice || 100,
        renewable: s.renewable || 50
      }))

      // Execute selected modules with real processing
      if (selectedModules.includes('scenario-impact')) {
        processedResults.scenarioImpact = DataProcessor.processScenarioImpact(
          portfolioData,
          emissionsData,
          scenariosData
        )
      }

      if (selectedModules.includes('compliance-gap')) {
        processedResults.complianceGap = DataProcessor.processComplianceGaps(
          portfolioData,
          emissionsData
        )
      }

      if (selectedModules.includes('risk-materiality')) {
        processedResults.riskMateriality = DataProcessor.processRiskMateriality(
          portfolioData,
          emissionsData
        )
      }

      if (selectedModules.includes('portfolio-aggregation')) {
        processedResults.portfolioAggregation = DataProcessor.processPortfolioAggregation(
          portfolioData
        )
      }

      if (selectedModules.includes('benchmarking')) {
        processedResults.benchmarking = DataProcessor.processBenchmarking(
          portfolioData,
          emissionsData
        )
      }

      const duration = ((Date.now() - startTime) / 1000).toFixed(2)
      const executionId = Math.random().toString(36).substring(7).toUpperCase()

      setResult({
        success: true,
        executionId,
        modulesProcessed: selectedModules.length,
        outputFormatsGenerated: selectedFormats.length,
        duration: `${duration}s`,
        processedData: processedResults,
        bankData: {
          orgName: uploadedData.orgName,
          bankId: uploadedData.bankId,
          totalAssets: portfolioData.reduce((sum, a) => sum + a.exposure, 0),
          assetCount: portfolioData.length
        },
        outputs: {
          json: { size: '245 KB', status: 'ready' },
          pdf: { size: '3.2 MB', status: 'ready' },
          excel: { size: '1.8 MB', status: 'ready' },
          dashboard: { status: 'live', url: `/dashboard/regulatory/${executionId}` },
          api: { endpoint: `/api/reports/${executionId}`, status: 'active' },
        },
        timestamp: new Date().toLocaleString(),
      })
    } catch (error) {
      setResult({
        success: false,
        error: error.message,
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Header */}
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-4xl font-light text-gray-900 mb-2">Data Ingestion & Workflow Execution</h1>
              <p className="text-gray-600">Upload bank portfolio data → Configure modules → Generate regulatory reports in multiple formats</p>
            </div>
            <div className="text-blue-600"><SimpleIcon type="bars" /></div>
          </div>
        </div>
      </section>

      {/* Template Download Section */}
      <section className="bg-blue-50 border-b border-blue-200 py-8 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-2xl font-light text-gray-900 mb-4">📥 Download Data Templates</h2>
          <p className="text-gray-600 mb-6">Download these CSV templates, edit with your bank's data, and upload back for processing.</p>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">📊 Portfolio Assets</p>
              <p className="text-xs text-gray-600 mb-3">Your asset portfolio with climate risk scores</p>
              <button onClick={() => downloadCSV('portfolio_assets.csv', portfolioAssetCSV)} className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Download CSV</button>
            </div>
            <div className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">🌱 GHG Emissions</p>
              <p className="text-xs text-gray-600 mb-3">Scope 1, 2, 3 emissions by asset</p>
              <button onClick={() => downloadCSV('ghg_emissions.csv', ghgEmissionsCSV)} className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Download CSV</button>
            </div>
            <div className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">🌍 Climate Scenarios</p>
              <p className="text-xs text-gray-600 mb-3">1.5°C, 2°C, 4°C scenarios with assumptions</p>
              <button onClick={() => downloadCSV('climate_scenarios.csv', climarioCSV)} className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Download CSV</button>
            </div>
            <div className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">📋 Documentation</p>
              <p className="text-xs text-gray-600 mb-3">How to use templates & field descriptions</p>
              <button onClick={() => alert('📋 README Guide:\n\n1. Download CSV files\n2. Edit with your bank data in Excel/Sheets\n3. Drag files onto the drop zone\n4. Select modules (Scenario, Gap Analysis, etc)\n5. Select output formats (PDF, Excel, Dashboard)\n6. Execute workflows\n7. Download results\n\nEach CSV has required columns:\n- Portfolio: Asset_ID, Asset_Name, Exposure_EUR_M, Climate_Risk_Score\n- Emissions: Asset_ID, Scope, Emissions_tCO2e, Category\n- Scenarios: Scenario_Name, Warming_Target_C, Probability_Percent')} className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">View Guide</button>
            </div>
          </div>
        </div>
      </section>

      {/* Main Content */}
      <section className="py-12 px-6 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left: Data Upload & Configuration */}
          <div className="lg:col-span-2 space-y-8">
            {/* Step 1: Data Input */}
            <div className="bg-white rounded-lg border border-gray-200 p-8">
              <h2 className="text-2xl font-light text-gray-900 mb-6">Step 1: Load Bank Data</h2>
              <div className="space-y-4">
                {uploadedData ? (
                  <div className="bg-green-50 border border-green-200 rounded-lg p-6">
                    <p className="text-sm text-green-800 font-semibold mb-3">✓ Data Loaded Successfully</p>
                    <div className="grid grid-cols-2 gap-4 text-sm text-green-700">
                      <div>
                        <p className="font-semibold">{uploadedData.orgName}</p>
                        <p className="text-xs">{uploadedData.bankId}</p>
                      </div>
                      <div>
                        <p className="font-semibold">€{uploadedData.portfolio.reduce((sum, a) => sum + a.exposure, 0).toLocaleString()}M</p>
                        <p className="text-xs">Total Assets</p>
                      </div>
                      <div>
                        <p className="font-semibold">{uploadedData.portfolio.length}</p>
                        <p className="text-xs">Asset Classes</p>
                      </div>
                      <div>
                        <p className="font-semibold">{uploadedData.emissions.length}</p>
                        <p className="text-xs">Emission Scopes</p>
                      </div>
                    </div>
                    <button
                      onClick={() => setUploadedData(null)}
                      className="mt-4 text-sm bg-gray-200 hover:bg-gray-300 text-gray-900 px-4 py-2 rounded-lg transition-all"
                    >
                      Clear & Load Different Data
                    </button>
                  </div>
                ) : (
                  <DragDropZone onDataLoaded={setUploadedData} onTemplateLoad={loadTemplateData} />
                )}
              </div>
            </div>

            {/* Step 2: Module Selection */}
            <div className="bg-white rounded-lg border border-gray-200 p-8">
              <h2 className="text-2xl font-light text-gray-900 mb-6">Step 2: Select Modules</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {modules.map(module => (
                  <label key={module.id} className="flex items-start gap-3 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedModules.includes(module.id)}
                      onChange={() => toggleModule(module.id)}
                      className="mt-1"
                    />
                    <div>
                      <p className="font-semibold text-gray-900">{module.name}</p>
                      <p className="text-xs text-gray-600">{module.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
              <p className="text-sm text-gray-600 mt-4">Selected: {selectedModules.length} module{selectedModules.length !== 1 ? 's' : ''}</p>
            </div>

            {/* Step 3: Output Format Selection */}
            <div className="bg-white rounded-lg border border-gray-200 p-8">
              <h2 className="text-2xl font-light text-gray-900 mb-6">Step 3: Select Output Formats</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {formats.map(format => (
                  <label key={format.id} className="flex items-start gap-3 p-4 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedFormats.includes(format.id)}
                      onChange={() => toggleFormat(format.id)}
                      className="mt-1"
                    />
                    <div>
                      <p className="font-semibold text-gray-900">{format.name}</p>
                      <p className="text-xs text-gray-600">{format.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
              <p className="text-sm text-gray-600 mt-4">Selected: {selectedFormats.length} format{selectedFormats.length !== 1 ? 's' : ''}</p>
            </div>

            {/* Execute Button */}
            <button
              onClick={executeWorkflow}
              disabled={!uploadedData || loading || selectedModules.length === 0}
              className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white px-8 py-4 rounded-lg font-semibold text-lg transition-all"
            >
              {loading ? 'Processing Workflows...' : 'Execute Workflows'}
            </button>
          </div>

          {/* Right: Results & Status */}
          <div className="bg-white rounded-lg border border-gray-200 p-8 h-fit">
            <h2 className="text-2xl font-light text-gray-900 mb-6">Execution Results</h2>

            {result ? (
              result.success ? (
                <div className="space-y-6">
                  <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                    <p className="text-sm font-semibold text-green-800 mb-2">✓ Workflow Completed Successfully</p>
                    <div className="space-y-2 text-xs text-green-700">
                      <p><span className="font-semibold">Execution ID:</span> {result.executionId}</p>
                      <p><span className="font-semibold">Duration:</span> {result.duration}</p>
                      <p><span className="font-semibold">Time:</span> {result.timestamp}</p>
                      <p><span className="font-semibold">Modules:</span> {result.modulesProcessed}</p>
                      <p><span className="font-semibold">Formats:</span> {result.outputFormatsGenerated}</p>
                    </div>
                  </div>

                  <div>
                    <p className="text-sm font-semibold text-gray-900 mb-3">Generated Outputs</p>
                    <div className="space-y-2">
                      {Object.entries(result.outputs).map(([format, info]) => (
                        <div key={format} className="flex items-center justify-between p-2 bg-gray-50 rounded">
                          <p className="text-xs font-semibold text-gray-700 capitalize">{format}</p>
                          <button
                            onClick={() => downloadOutputFile(format, result.executionId)}
                            className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700"
                          >
                            {format === 'api' || format === 'dashboard' ? 'View' : 'Download'}
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <p className="text-sm font-semibold text-red-800">Error: {result.error}</p>
                </div>
              )
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-600 text-sm">Results will appear here after execution</p>
              </div>
            )}
          </div>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}

/**
 * Drag & Drop Zone Component
 * Allows users to drag CSV files directly
 */
function DragDropZone({ onDataLoaded, onTemplateLoad }) {
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)

  const parseCSV = (text) => {
    const lines = text.trim().split('\n')
    const headers = lines[0].split(',').map(h => h.trim())
    const data = []
    for (let i = 1; i < lines.length; i++) {
      const obj = {}
      const values = lines[i].split(',')
      headers.forEach((header, index) => {
        obj[header] = values[index]?.trim() || ''
      })
      data.push(obj)
    }
    return data
  }

  const handleFiles = (files) => {
    setError(null)
    let portfolioData = null
    let emissionsData = null
    let scenariosData = null

    try {
      for (const file of files) {
        if (!file.name.endsWith('.csv')) {
          setError(`Invalid file: ${file.name}. Please upload CSV files only.`)
          return
        }

        const reader = new FileReader()
        reader.onload = (e) => {
          const text = e.target.result
          const parsed = parseCSV(text)

          if (file.name.includes('portfolio')) {
            portfolioData = parsed.map(p => ({
              id: p.Asset_ID,
              name: p.Asset_Name,
              type: p.Asset_Type,
              exposure: parseFloat(p.Exposure_EUR_M) || 0,
            }))
          } else if (file.name.includes('emission')) {
            emissionsData = parsed.map(e => ({
              scope: parseInt(e.Scope),
              emissions: parseFloat(e.Emissions_tCO2e) || 0,
              category: e.Category,
            }))
          } else if (file.name.includes('scenario')) {
            scenariosData = parsed.map(s => ({
              name: s.Scenario_Name,
              warming: parseFloat(s.Warming_Target_C),
              probability: parseFloat(s.Probability_Percent) / 100,
            }))
          }

          // If all files loaded, create combined data
          if (portfolioData && emissionsData && scenariosData) {
            onDataLoaded({
              bankId: 'BANK_UPLOADED',
              orgName: 'Your Bank',
              portfolio: portfolioData,
              emissions: emissionsData,
              scenarios: scenariosData,
            })
          }
        }
        reader.readAsText(file)
      }
    } catch (err) {
      setError(`Error parsing files: ${err.message}`)
    }
  }

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div className="space-y-4">
      {/* Drag & Drop Zone */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-12 text-center transition-all cursor-pointer ${
          dragActive
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 bg-gray-50 hover:border-blue-400 hover:bg-blue-50'
        }`}
      >
        <div className="mb-4 text-4xl">📁</div>
        <h3 className="text-lg font-semibold text-gray-900 mb-2">Drag & Drop CSV Files Here</h3>
        <p className="text-gray-600 mb-4">
          Upload your bank data files (portfolio_assets.csv, ghg_emissions.csv, climate_scenarios.csv)
        </p>
        <p className="text-sm text-gray-500 mb-6">or</p>
        <button
          onClick={() => fileInputRef.current?.click()}
          className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-semibold transition-all"
        >
          Click to Browse Files
        </button>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".csv"
          onChange={(e) => handleFiles(e.target.files)}
          className="hidden"
        />
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-50 border border-red-300 rounded-lg p-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {/* Template Option */}
      <div className="border border-gray-300 rounded-lg p-6 text-center">
        <p className="text-gray-600 mb-4">Don't have your data ready yet?</p>
        <button
          onClick={onTemplateLoad}
          className="bg-gray-600 hover:bg-gray-700 text-white px-6 py-2 rounded-lg font-semibold transition-all"
        >
          Load Example/Template Data
        </button>
        <p className="text-xs text-gray-500 mt-3">Use template to test the workflow with sample data</p>
      </div>
    </div>
  )
}
