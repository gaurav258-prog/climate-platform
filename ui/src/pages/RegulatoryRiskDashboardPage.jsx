
import { useEffect, useState } from 'react'
import SimpleIcon from '../components/SimpleIcon'
import WorkflowResultsStorage from '../services/WorkflowResultsStorage'

export default function RegulatoryRiskDashboardPage() {
  const [riskMetrics, setRiskMetrics] = useState({
    physicalRisk: 45,
    transitionRisk: 68,
    regulatoryRisk: 54,
    reputationalRisk: 32
  })
  const [complianceStatus, setComplianceStatus] = useState({
    tcfd: { complete: 95, status: 'Complete' },
    taxonomy: { complete: 58, status: 'In Progress' },
    sec: { complete: 65, status: 'In Progress' }
  })
  const [portfolioRisk, setPortfolioRisk] = useState([
    { sector: 'Oil & Gas', flood: 8, heat: 7, wildfire: 9, seismic: 4 },
    { sector: 'Real Estate', flood: 6, heat: 8, wildfire: 5, seismic: 6 },
    { sector: 'Agriculture', flood: 9, heat: 9, wildfire: 6, seismic: 3 },
    { sector: 'Manufacturing', flood: 4, heat: 5, wildfire: 3, seismic: 7 },
  ])
  const [scenarios, setScenarios] = useState(null)
  const [hasData, setHasData] = useState(false)

  useEffect(() => {
    // Load data from workflow results storage
    if (WorkflowResultsStorage.hasRecentResults()) {
      const metrics = WorkflowResultsStorage.calculateRiskMetrics()
      const compliance = WorkflowResultsStorage.getComplianceStatus()
      const portfolio = WorkflowResultsStorage.getPortfolioRiskBySector()
      const scenarioData = WorkflowResultsStorage.getScenarioComparison()

      setRiskMetrics(metrics)
      setComplianceStatus(compliance)
      setPortfolioRisk(portfolio)
      setScenarios(scenarioData)
      setHasData(true)
    }
  }, [])

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Regulatory Risk Dashboard</h1>
            <p className="text-gray-600">
              {hasData ? 'Live execution results' : 'Sample data (run a workflow to see live results)'}
            </p>
          </div>
          <div><SimpleIcon type="bars" /></div>
        </div>
      </section>

      <section className="py-12 px-6 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-6">Risk Exposure Summary</h2>
            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Physical Risk</p>
                  <p className="text-sm font-semibold text-red-600">{riskMetrics.physicalRisk > 60 ? 'High' : riskMetrics.physicalRisk > 40 ? 'Medium' : 'Low'}</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-red-600" style={{width: `${riskMetrics.physicalRisk}%`}} />
                </div>
                <p className="text-xs text-gray-500 mt-1">{riskMetrics.physicalRisk}%</p>
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Transition Risk</p>
                  <p className="text-sm font-semibold text-orange-600">{riskMetrics.transitionRisk > 60 ? 'High' : riskMetrics.transitionRisk > 40 ? 'Medium' : 'Low'}</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-orange-600" style={{width: `${riskMetrics.transitionRisk}%`}} />
                </div>
                <p className="text-xs text-gray-500 mt-1">{riskMetrics.transitionRisk}%</p>
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Regulatory Risk</p>
                  <p className="text-sm font-semibold text-yellow-600">{riskMetrics.regulatoryRisk > 60 ? 'High' : riskMetrics.regulatoryRisk > 40 ? 'Medium' : 'Low'}</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-yellow-600" style={{width: `${riskMetrics.regulatoryRisk}%`}} />
                </div>
                <p className="text-xs text-gray-500 mt-1">{riskMetrics.regulatoryRisk}%</p>
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Reputational Risk</p>
                  <p className="text-sm font-semibold text-green-600">{riskMetrics.reputationalRisk > 60 ? 'High' : riskMetrics.reputationalRisk > 40 ? 'Medium' : 'Low'}</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-green-600" style={{width: `${riskMetrics.reputationalRisk}%`}} />
                </div>
                <p className="text-xs text-gray-500 mt-1">{riskMetrics.reputationalRisk}%</p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-6">Compliance Status</h2>
            <div className="space-y-4">
              <div className={`flex items-center justify-between p-4 rounded-lg border ${complianceStatus.tcfd.complete >= 90 ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'}`}>
                <div>
                  <p className={`font-semibold ${complianceStatus.tcfd.complete >= 90 ? 'text-green-900' : 'text-yellow-900'}`}>TCFD</p>
                  <p className={`text-sm ${complianceStatus.tcfd.complete >= 90 ? 'text-green-700' : 'text-yellow-700'}`}>{complianceStatus.tcfd.complete}% Complete</p>
                </div>
                <span className="text-2xl">{complianceStatus.tcfd.complete >= 90 ? '✓' : '⚠'}</span>
              </div>
              <div className={`flex items-center justify-between p-4 rounded-lg border ${complianceStatus.taxonomy.complete >= 80 ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'}`}>
                <div>
                  <p className={`font-semibold ${complianceStatus.taxonomy.complete >= 80 ? 'text-green-900' : 'text-yellow-900'}`}>EU Taxonomy</p>
                  <p className={`text-sm ${complianceStatus.taxonomy.complete >= 80 ? 'text-green-700' : 'text-yellow-700'}`}>{complianceStatus.taxonomy.complete}% Complete</p>
                </div>
                <span className="text-2xl">{complianceStatus.taxonomy.complete >= 80 ? '✓' : '⚠'}</span>
              </div>
              <div className={`flex items-center justify-between p-4 rounded-lg border ${complianceStatus.sec.complete >= 80 ? 'bg-green-50 border-green-200' : 'bg-orange-50 border-orange-200'}`}>
                <div>
                  <p className={`font-semibold ${complianceStatus.sec.complete >= 80 ? 'text-green-900' : 'text-orange-900'}`}>SEC Disclosure</p>
                  <p className={`text-sm ${complianceStatus.sec.complete >= 80 ? 'text-green-700' : 'text-orange-700'}`}>{complianceStatus.sec.complete}% Complete</p>
                </div>
                <span className="text-2xl">{complianceStatus.sec.complete >= 80 ? '✓' : '⚠'}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 bg-white rounded-lg border border-gray-200 p-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">Portfolio Risk Heatmap by Sector</h2>
          <div className="space-y-4">
            {portfolioRisk.map((row, idx) => (
              <div key={idx} className="flex items-center gap-4">
                <p className="font-semibold text-gray-900 w-32">{row.sector}</p>
                <div className="flex gap-2 flex-1">
                  {[
                    { label: 'Physical', value: row.physicalRisk || 0, color: 'bg-red-600' },
                    { label: 'Transition', value: row.transitionRisk || 0, color: 'bg-orange-600' },
                  ].map((risk) => (
                    <div key={risk.label} className="flex-1 text-center">
                      <div className={`${risk.color} h-8 rounded flex items-center justify-center text-white text-sm font-semibold`}>
                        {risk.value}
                      </div>
                      <p className="text-xs text-gray-600 mt-1">{risk.label}</p>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
