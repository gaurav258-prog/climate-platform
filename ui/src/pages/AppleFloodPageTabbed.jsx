import { useState, useEffect } from 'react'
import { Waves, TrendingUp, AlertTriangle, Activity, ChevronRight } from 'lucide-react'
import RiskMap from '../components/RiskMap'

/**
 * Tabbed Flood Risk Dashboard
 * - Animated water background
 * - Clickable tab navigation
 * - Map view with danger zones
 * - Risk analysis by basin
 */
export default function AppleFloodPageTabbed() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState({
    activeFloods: 0,
    affectedRegions: 0,
    avgRisk: 0,
    populationAtRisk: 0
  })
  const [selectedBasin, setSelectedBasin] = useState(null)

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
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'map', label: 'Flood Map', icon: Waves },
    { id: 'basins', label: 'Basins', icon: AlertTriangle },
    { id: 'analysis', label: 'Analysis', icon: TrendingUp },
  ]

  return (
    <div className="w-full h-full overflow-y-auto bg-white">
      {/* Animated Water Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(circle at 20% 50%, rgba(59, 130, 246, 0.08), transparent 50%), radial-gradient(circle at 80% 80%, rgba(6, 182, 212, 0.06), transparent 50%)',
            animation: 'float 12s ease-in-out infinite'
          }}
        />
        {/* Water wave pattern */}
        <svg className="absolute inset-0 w-full h-full opacity-5" viewBox="0 0 1200 600">
          <defs>
            <pattern id="water" patternUnits="userSpaceOnUse" width="100" height="100">
              <path
                d="M0,50 Q25,40 50,50 T100,50"
                stroke="#3b82f6"
                strokeWidth="2"
                fill="none"
                opacity="0.3"
              />
            </pattern>
          </defs>
          <rect width="1200" height="600" fill="url(#water)" />
        </svg>
      </div>

      {/* Main Content */}
      <div className="relative z-10 w-full">
        {/* Header */}
        <header className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-6 py-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-light text-gray-900">🌊 Flood Intelligence</h1>
                <p className="text-sm text-gray-600 mt-1">Real-time flood risk assessment and early warning systems</p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-1 border-b border-gray-200 -mx-6 px-6">
              {tabs.map((tab) => {
                const Icon = tab.icon
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`px-4 py-3 flex items-center gap-2 border-b-2 transition-all font-medium text-sm ${
                      activeTab === tab.id
                        ? 'border-blue-600 text-blue-600'
                        : 'border-transparent text-gray-600 hover:text-gray-900'
                    }`}
                  >
                    <Icon size={16} />
                    {tab.label}
                  </button>
                )
              })}
            </div>
          </div>
        </header>

        {/* Overview Tab */}
        {activeTab === 'overview' && (
          <section className="max-w-7xl mx-auto px-6 py-12">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-12">
              <div className="bg-white rounded-2xl p-6 border border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-1">ACTIVE FLOODS</p>
                    <p className="text-4xl font-light text-gray-900">{stats.activeFloods}</p>
                    <p className="text-xs text-gray-500 mt-2">Current events</p>
                  </div>
                  <Activity className="text-blue-600" size={24} />
                </div>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-1">AFFECTED REGIONS</p>
                    <p className="text-4xl font-light text-gray-900">{stats.affectedRegions}</p>
                    <p className="text-xs text-gray-500 mt-2">River basins</p>
                  </div>
                  <Waves className="text-cyan-600" size={24} />
                </div>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-1">AVG RISK LEVEL</p>
                    <p className="text-4xl font-light text-gray-900">{stats.avgRisk}/100</p>
                    <p className="text-xs text-gray-500 mt-2">Basin average</p>
                  </div>
                  <TrendingUp className="text-blue-600" size={24} />
                </div>
              </div>

              <div className="bg-gradient-to-br from-blue-50 to-cyan-50 rounded-2xl p-6 border border-blue-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-blue-600 font-medium mb-1">POPULATION AT RISK</p>
                    <p className="text-3xl font-light text-blue-600">
                      {(stats.populationAtRisk / 1000000).toFixed(1)}M
                    </p>
                    <p className="text-xs text-blue-500 mt-2">Total exposure</p>
                  </div>
                  <AlertTriangle className="text-blue-600" size={24} />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h2 className="text-2xl font-light text-gray-900 mb-6">Flood Risk Management</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Detection</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Real-time monitoring of river discharge, rainfall patterns, and water levels. Early warning systems detect flood conditions hours before peak flow.
                  </p>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Forecasting</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Hydrological models predict flood extent, duration, and impact. We calculate inundation depth and affected infrastructure with 72-hour advance notice.
                  </p>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Response</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Automated alerts to emergency services, population evacuation routes, and infrastructure protection recommendations based on real-time impact assessment.
                  </p>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Map Tab */}
        {activeTab === 'map' && (
          <section className="w-full h-[calc(100vh-200px)]">
            <RiskMap />
          </section>
        )}

        {/* Basins Tab */}
        {activeTab === 'basins' && (
          <section className="max-w-7xl mx-auto px-6 py-12">
            <h2 className="text-3xl font-light text-gray-900 mb-8">River Basins at Risk</h2>

            <div className="space-y-4">
              {basins.map((basin) => (
                <div
                  key={basin.id}
                  onClick={() => setSelectedBasin(basin)}
                  className={`bg-white rounded-2xl p-6 border-2 cursor-pointer transition-all ${
                    selectedBasin?.id === basin.id
                      ? 'border-blue-600 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900">{basin.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">{basin.trend}</p>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">FLOOD RISK</p>
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-cyan-500 to-blue-600"
                            style={{ width: `${basin.risk}%` }}
                          />
                        </div>
                        <p className="text-lg font-semibold text-blue-600 w-12">{basin.risk}</p>
                      </div>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">FLOOD EVENTS</p>
                      <p className="text-3xl font-light text-gray-900">{basin.events}</p>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">POPULATION</p>
                      <p className="text-xl font-semibold text-gray-900">
                        {(basin.population / 1000000).toFixed(1)}M
                      </p>
                    </div>

                    <div className="text-right">
                      <ChevronRight className="text-gray-400 ml-auto" size={24} />
                    </div>
                  </div>

                  {selectedBasin?.id === basin.id && (
                    <div className="mt-6 pt-6 border-t border-blue-200">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Peak Discharge</p>
                          <p className="text-2xl font-light text-blue-600">12,500 m³/s</p>
                          <p className="text-xs text-gray-500 mt-1">Current forecast</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Inundation Area</p>
                          <p className="text-2xl font-light">450 km²</p>
                          <p className="text-xs text-gray-500 mt-1">Expected extent</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Warning Time</p>
                          <p className="text-2xl font-light text-green-600">48 hours</p>
                          <p className="text-xs text-gray-500 mt-1">Advance notice</p>
                        </div>
                      </div>
                      <button className="mt-6 w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors">
                        View Hydrograph →
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Analysis Tab */}
        {activeTab === 'analysis' && (
          <section className="max-w-7xl mx-auto px-6 py-12">
            <h2 className="text-3xl font-light text-gray-900 mb-8">Flood Risk Analysis</h2>

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
                  <div>
                    <p className="text-sm text-gray-600 mb-2">Thames (Low)</p>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-2/5 h-full bg-cyan-300" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-2xl border border-gray-200 p-8">
                <h3 className="text-xl font-semibold text-gray-900 mb-6">Forecast Skill</h3>
                <div className="space-y-6">
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">7-day Flood Prediction</p>
                      <p className="text-sm font-semibold text-gray-900">68%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-68/100 h-full bg-blue-600" />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">Discharge Forecast</p>
                      <p className="text-sm font-semibold text-gray-900">±15%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-4/5 h-full bg-green-600" />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">Inundation Extent</p>
                      <p className="text-sm font-semibold text-gray-900">±8%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-4/5 h-full bg-green-600" />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Footer spacing */}
        <div className="h-20" />
      </div>

      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(30px); }
        }
      `}</style>
    </div>
  )
}
