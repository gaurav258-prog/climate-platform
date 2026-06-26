import { useState } from 'react'
import SimpleIcon from '../components/SimpleIcon'

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

  const executeWorkflow = async () => {
    if (!uploadedData) {
      alert('Please load data first')
      return
    }

    setLoading(true)
    setResult(null)

    try {
      // Simulate workflow execution
      await new Promise(resolve => setTimeout(resolve, 2000))

      setResult({
        success: true,
        executionId: Math.random().toString(36).substring(7).toUpperCase(),
        modulesProcessed: selectedModules.length,
        outputFormatsGenerated: selectedFormats.length,
        duration: '2.3s',
        outputs: {
          json: { size: '245 KB', status: 'ready' },
          pdf: { size: '3.2 MB', status: 'ready' },
          excel: { size: '1.8 MB', status: 'ready' },
          dashboard: { status: 'live' },
          api: { endpoint: '/api/reports', status: 'active' },
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
            <a href="/data-templates/portfolio_assets.csv" download className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">📊 Portfolio Assets</p>
              <p className="text-xs text-gray-600 mb-3">Your asset portfolio with climate risk scores</p>
              <button className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Download CSV</button>
            </a>
            <a href="/data-templates/ghg_emissions.csv" download className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">🌱 GHG Emissions</p>
              <p className="text-xs text-gray-600 mb-3">Scope 1, 2, 3 emissions by asset</p>
              <button className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Download CSV</button>
            </a>
            <a href="/data-templates/climate_scenarios.csv" download className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">🌍 Climate Scenarios</p>
              <p className="text-xs text-gray-600 mb-3">1.5°C, 2°C, 4°C scenarios with assumptions</p>
              <button className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Download CSV</button>
            </a>
            <a href="/data-templates/README.md" download className="bg-white p-4 rounded-lg border border-blue-300 hover:shadow-md transition-all">
              <p className="font-semibold text-gray-900 mb-2">📋 Documentation</p>
              <p className="text-xs text-gray-600 mb-3">How to use templates & field descriptions</p>
              <button className="text-xs bg-blue-600 text-white px-3 py-1 rounded hover:bg-blue-700">Download Guide</button>
            </a>
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
                  </div>
                ) : (
                  <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
                    <p className="text-gray-600 mb-4">No data uploaded yet</p>
                    <button
                      onClick={loadTemplateData}
                      className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-semibold transition-all"
                    >
                      Load Template Data
                    </button>
                  </div>
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
                          <button className="text-xs bg-blue-600 text-white px-2 py-1 rounded hover:bg-blue-700">
                            Download
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
