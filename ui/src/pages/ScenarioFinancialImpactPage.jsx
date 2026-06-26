import { useState } from 'react'
import SimpleIcon from '../components/SimpleIcon'

}

/**
 * Scenario Financial Impact Analysis
 * Calculate projected revenue, NPV, and stranded asset risk
 */
export default function ScenarioFinancialImpactPage() {
  const [selectedScenario, setSelectedScenario] = useState('1.5c')

  const scenarios = [
    {
      id: '1.5c',
      name: '1.5°C Pathway',
      description: 'Paris Agreement aligned, rapid transition',
      color: 'text-green-600',
      bgColor: 'bg-green-50'
    },
    {
      id: '2c',
      name: '2°C Scenario',
      description: 'Current policies trajectory',
      color: 'text-yellow-600',
      bgColor: 'bg-yellow-50'
    },
    {
      id: '4c',
      name: '4°C+ (No Action)',
      description: 'Business as usual, high warming',
      color: 'text-red-600',
      bgColor: 'bg-red-50'
    }
  ]

  const timeHorizons = ['2025', '2030', '2040', '2050']

  const impacts = {
    '1.5c': {
      revenue_impact: [-5, -12, -28, -35],
      npv: [2400, 1800, 900, 200],
      stranded_assets: [150, 450, 1200, 2100]
    },
    '2c': {
      revenue_impact: [-3, -8, -18, -25],
      npv: [2900, 2400, 1600, 800],
      stranded_assets: [100, 280, 800, 1500]
    },
    '4c': {
      revenue_impact: [-1, -2, -4, -8],
      npv: [3200, 3000, 2800, 2500],
      stranded_assets: [50, 80, 150, 300]
    }
  }

  const current = impacts[selectedScenario]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Header */}
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-4xl font-light text-gray-900 mb-2">Scenario Financial Impact</h1>
              <p className="text-gray-600">Calculate projected revenue impact, NPV, and stranded assets across climate scenarios</p>
            </div>
            <div className="text-blue-600"><SimpleIcon type="bars" /></div>
          </div>
        </div>
      </section>

      {/* Scenario Selection */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <h2 className="text-2xl font-light text-gray-900 mb-6">Select Scenario</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {scenarios.map((scenario) => (
            <button
              key={scenario.id}
              onClick={() => setSelectedScenario(scenario.id)}
              className={`rounded-lg border-2 p-6 text-left transition-all ${
                selectedScenario === scenario.id
                  ? `${scenario.bgColor} border-gray-400 shadow-md`
                  : 'bg-white border-gray-200 hover:border-gray-300'
              }`}
            >
              <h3 className={`text-lg font-semibold mb-2 ${scenario.color}`}>{scenario.name}</h3>
              <p className="text-sm text-gray-600">{scenario.description}</p>
            </button>
          ))}
        </div>
      </section>

      {/* Analysis Charts */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <h2 className="text-2xl font-light text-gray-900 mb-6">Financial Projections</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Revenue Impact */}
          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-gray-900">Revenue Impact (%)</h3>
              <div><SimpleIcon type="trend" /></div>
            </div>
            <div className="space-y-4">
              {timeHorizons.map((year, idx) => (
                <div key={year}>
                  <div className="flex justify-between mb-1">
                    <p className="text-sm text-gray-600">{year}</p>
                    <p className="text-sm font-semibold text-red-600">{current.revenue_impact[idx]}%</p>
                  </div>
                  <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-red-600"
                      style={{ width: `${Math.abs(current.revenue_impact[idx]) * 2}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* NPV Projection */}
          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-gray-900">NPV (€M)</h3>
              <div><SimpleIcon type="bars" /></div>
            </div>
            <div className="space-y-4">
              {timeHorizons.map((year, idx) => (
                <div key={year}>
                  <div className="flex justify-between mb-1">
                    <p className="text-sm text-gray-600">{year}</p>
                    <p className="text-sm font-semibold text-blue-600">€{current.npv[idx]}M</p>
                  </div>
                  <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-600"
                      style={{ width: `${(current.npv[idx] / 3500) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Stranded Assets */}
          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-lg font-semibold text-gray-900">Stranded Assets (€M)</h3>
              <div><SimpleIcon type="bars" /></div>
            </div>
            <div className="space-y-4">
              {timeHorizons.map((year, idx) => (
                <div key={year}>
                  <div className="flex justify-between mb-1">
                    <p className="text-sm text-gray-600">{year}</p>
                    <p className="text-sm font-semibold text-orange-600">€{current.stranded_assets[idx]}M</p>
                  </div>
                  <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-orange-600"
                      style={{ width: `${(current.stranded_assets[idx] / 2500) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Summary Box */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-blue-50 border border-blue-300 rounded-lg p-8">
          <h3 className="text-lg font-semibold text-blue-900 mb-4">Key Findings</h3>
          <ul className="space-y-2 text-blue-800 text-sm">
            <li>✓ {selectedScenario === '1.5c' ? 'Aggressive transition' : selectedScenario === '2c' ? 'Moderate transition' : 'Minimal climate action'} scenario selected</li>
            <li>✓ Revenue impact ranges from {Math.min(...current.revenue_impact)}% to {Math.max(...current.revenue_impact)}% by 2050</li>
            <li>✓ NPV declines from €{current.npv[0]}M to €{current.npv[3]}M</li>
            <li>✓ Stranded assets exposure: €{current.stranded_assets[3]}M by 2050</li>
            <li>✓ Requires strategic asset reallocation and portfolio transition</li>
          </ul>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
