import { useState, useEffect } from 'react'
import { Waves, TrendingUp, AlertTriangle, Activity, ChevronRight } from 'lucide-react'
import RiskMap from '../components/RiskMap'

/**
 * Flood Risk Dashboard - Scrollable with Tabs
 * Hero + Animated Background → Tabs → Content → Full Map
 */
export default function AppleFloodPageTabbed() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState({
    activeFloods: 0,
    affectedRegions: 0,
    avgRisk: 0,
    populationAtRisk: 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      setStats({
        activeFloods: Math.floor(Math.random() * 50) + 20,
        affectedRegions: Math.floor(Math.random() * 15) + 5,
        avgRisk: Math.floor(Math.random() * 40) + 40,
        populationAtRisk: Math.floor(Math.random() * 5000000) + 1000000
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const basins = [
    { id: 1, name: 'Rhine Basin', risk: 78, events: 23, population: 1200000, trend: '↑ Increasing' },
    { id: 2, name: 'Danube Basin', risk: 65, events: 18, population: 2100000, trend: '→ Stable' },
    { id: 3, name: 'Thames Basin', risk: 42, events: 8, population: 800000, trend: '↓ Decreasing' },
    { id: 4, name: 'Po Valley', risk: 72, events: 21, population: 3500000, trend: '↑ Increasing' },
    { id: 5, name: 'Loire Basin', risk: 55, events: 12, population: 1400000, trend: '→ Stable' },
  ]

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'basins', label: 'Basins' },
    { id: 'analysis', label: 'Analysis' },
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-white">
      {/* Animated Gradient Background */}
      <div className="fixed inset-0 pointer-events-none -z-10 bg-gradient-to-br from-blue-900 via-blue-700 to-cyan-500" />
      <div className="fixed inset-0 pointer-events-none -z-10">
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(circle at 20% 50%, rgba(59, 130, 246, 0.3), transparent 50%), radial-gradient(circle at 80% 80%, rgba(6, 182, 212, 0.2), transparent 50%)',
            animation: 'float 8s ease-in-out infinite'
          }}
        />
      </div>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-12 pb-20">
        <div className="text-center px-6 max-w-4xl mx-auto w-full">
          <div className="text-7xl mb-4">🌊</div>
          <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
            Flood
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-cyan-500">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Real-time flood risk assessment, hydrological forecasting, and early warning systems
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-blue-600">{stats.activeFloods}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Active Floods</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-cyan-600">{stats.affectedRegions}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Regions</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-blue-500">{stats.avgRisk}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Avg Risk</div>
            </div>
            <div className="text-center">
              <div className="text-2xl md:text-3xl font-light text-blue-600">
                {(stats.populationAtRisk / 1000000).toFixed(1)}M
              </div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Population</div>
            </div>
          </div>
        </div>
      </section>

      {/* Tabs Section */}
      <section className="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6">
          <div className="flex gap-8">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 font-medium text-sm border-b-2 transition-all ${
                  activeTab === tab.id
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-600 hover:text-gray-900'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Tab Content Area */}
      <section className="max-w-7xl mx-auto px-6 py-12">
        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <div className="space-y-12">
            <div>
              <h2 className="text-3xl font-light text-gray-900 mb-8">Flood Risk Management</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Detection</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Real-time monitoring of river discharge, rainfall patterns, and water levels. Early warning systems detect flood conditions hours before peak flow.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Forecasting</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Hydrological models predict flood extent, duration, and impact. We calculate inundation depth and affected infrastructure with 72-hour advance notice.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Response</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Automated alerts to emergency services, population evacuation routes, and infrastructure protection recommendations based on real-time impact assessment.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Basins Tab */}
        {activeTab === 'basins' && (
          <div>
            <h2 className="text-3xl font-light text-gray-900 mb-8">River Basins at Risk</h2>
            <div className="space-y-4">
              {basins.map((basin) => (
                <div key={basin.id} className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-blue-300 hover:shadow-lg transition-all">
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900">{basin.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">{basin.trend}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-2">FLOOD RISK</p>
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-cyan-500 to-blue-600"
                            style={{ width: `${basin.risk}%` }}
                          />
                        </div>
                        <span className="text-lg font-semibold text-blue-600 w-12">{basin.risk}</span>
                      </div>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">EVENTS</p>
                      <p className="text-2xl font-light text-gray-900">{basin.events}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">POPULATION</p>
                      <p className="text-lg font-semibold">{(basin.population / 1000000).toFixed(1)}M</p>
                    </div>
                    <div className="text-right">
                      <ChevronRight className="text-gray-400" size={24} />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Analysis Tab */}
        {activeTab === 'analysis' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h3 className="text-xl font-semibold text-gray-900 mb-6">Basin Flood Hazard</h3>
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-gray-600 mb-2">Rhine (Very High)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-5/5 h-full bg-blue-600" />
                  </div>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Po Valley (High)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-4/5 h-full bg-cyan-500" />
                  </div>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Danube (Moderate)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-3/5 h-full bg-blue-400" />
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h3 className="text-xl font-semibold text-gray-900 mb-6">Forecast Skill</h3>
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">7-day Prediction</p>
                    <p className="text-sm font-semibold">68%</p>
                  </div>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-68/100 h-full bg-blue-600" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">Discharge Forecast</p>
                    <p className="text-sm font-semibold">±15%</p>
                  </div>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-4/5 h-full bg-green-600" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Full Map Section - Always Visible */}
      <section className="py-20 px-6 max-w-7xl mx-auto w-full">
        <h2 className="text-3xl font-light text-gray-900 mb-8">Real-time Flood Risk Map</h2>
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden" style={{ height: '600px' }}>
          <RiskMap />
        </div>
      </section>

      {/* Footer */}
      <div className="h-20" />

      <style>{`
        @keyframes gradientShift {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(30px); }
        }
      `}</style>
    </div>
  )
}
