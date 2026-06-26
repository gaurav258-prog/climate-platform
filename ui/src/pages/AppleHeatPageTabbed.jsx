import { useState, useEffect } from 'react'
import { Thermometer, TrendingUp, AlertTriangle, Activity, ChevronRight } from 'lucide-react'

/**
 * Tabbed Heat Stress Risk Dashboard
 * - Animated heat background
 * - Clickable tab navigation
 * - Map view with temperature zones
 * - Risk analysis by region
 */
export default function AppleHeatPageTabbed() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState({
    extremeHeatEvents: 0,
    affectedRegions: 0,
    avgRisk: 0,
    populationAtRisk: 0
  })
  const [selectedRegion, setSelectedRegion] = useState(null)

  useEffect(() => {
    const interval = setInterval(() => {
      setStats({
        extremeHeatEvents: Math.floor(Math.random() * 30) + 10,
        affectedRegions: Math.floor(Math.random() * 12) + 5,
        avgRisk: Math.floor(Math.random() * 45) + 45,
        populationAtRisk: Math.floor(Math.random() * 100000000) + 50000000
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const regions = [
    { id: 1, name: 'Southern Mediterranean', risk: 89, events: 28, temp: 42, trend: '↑ Increasing' },
    { id: 2, name: 'Iberian Peninsula', risk: 85, events: 25, temp: 41, trend: '↑ Increasing' },
    { id: 3, name: 'Greece & Balkans', risk: 78, events: 20, temp: 39, trend: '↑ Increasing' },
    { id: 4, name: 'Central Europe', risk: 52, events: 12, temp: 35, trend: '→ Stable' },
    { id: 5, name: 'Northern Europe', risk: 35, events: 6, temp: 30, trend: '↓ Decreasing' },
  ]

  const tabs = [
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'map', label: 'Heat Map', icon: Thermometer },
    { id: 'regions', label: 'Regions', icon: AlertTriangle },
    { id: 'analysis', label: 'Analysis', icon: TrendingUp },
  ]

  return (
    <div className="w-full h-full overflow-y-auto bg-white">
      {/* Animated Heat Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(circle at 20% 50%, rgba(251, 191, 36, 0.08), transparent 50%), radial-gradient(circle at 80% 80%, rgba(249, 115, 22, 0.06), transparent 50%)',
            animation: 'float 12s ease-in-out infinite'
          }}
        />
        {/* Heat wave pattern */}
        <svg className="absolute inset-0 w-full h-full opacity-5" viewBox="0 0 1200 600">
          <defs>
            <pattern id="heat" patternUnits="userSpaceOnUse" width="100" height="100">
              <path
                d="M0,50 Q25,35 50,50 T100,50"
                stroke="#fbbf24"
                strokeWidth="2"
                fill="none"
                opacity="0.3"
              />
            </pattern>
          </defs>
          <rect width="1200" height="600" fill="url(#heat)" />
        </svg>
      </div>

      {/* Main Content */}
      <div className="relative z-10 w-full">
        {/* Header */}
        <header className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-6 py-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-light text-gray-900">☀️ Heat Stress Intelligence</h1>
                <p className="text-sm text-gray-600 mt-1">Monitor extreme heat events and health risks</p>
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
                        ? 'border-yellow-600 text-yellow-600'
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
                    <p className="text-sm text-gray-600 font-medium mb-1">HEAT WAVES</p>
                    <p className="text-4xl font-light text-gray-900">{stats.extremeHeatEvents}</p>
                    <p className="text-xs text-gray-500 mt-2">Current events</p>
                  </div>
                  <Activity className="text-yellow-600" size={24} />
                </div>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-1">AFFECTED REGIONS</p>
                    <p className="text-4xl font-light text-gray-900">{stats.affectedRegions}</p>
                    <p className="text-xs text-gray-500 mt-2">High heat zones</p>
                  </div>
                  <Thermometer className="text-orange-600" size={24} />
                </div>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-1">AVG RISK LEVEL</p>
                    <p className="text-4xl font-light text-gray-900">{stats.avgRisk}/100</p>
                    <p className="text-xs text-gray-500 mt-2">Regional average</p>
                  </div>
                  <TrendingUp className="text-yellow-600" size={24} />
                </div>
              </div>

              <div className="bg-gradient-to-br from-yellow-50 to-orange-50 rounded-2xl p-6 border border-yellow-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-yellow-600 font-medium mb-1">POPULATION AT RISK</p>
                    <p className="text-3xl font-light text-yellow-600">
                      {(stats.populationAtRisk / 1000000).toFixed(0)}M
                    </p>
                    <p className="text-xs text-yellow-500 mt-2">Exposure</p>
                  </div>
                  <AlertTriangle className="text-yellow-600" size={24} />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h2 className="text-2xl font-light text-gray-900 mb-6">Heat Stress Monitoring</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Detection</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Real-time temperature monitoring from weather stations and satellites. Heat wave identification based on temperature anomalies and duration thresholds.
                  </p>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Health Impact</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Estimate excess mortality risk based on temperature, humidity, and vulnerable population distribution. Calculate strain on healthcare systems.
                  </p>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Response</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Automated alerts to public health agencies and vulnerable groups. Cool center location recommendations and medical resource allocation.
                  </p>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* Map Tab */}
        {activeTab === 'map' && (
          <section className="w-full h-[calc(100vh-200px)] flex items-center justify-center">
            <div className="text-center">
              <Thermometer size={64} className="mx-auto text-yellow-300 mb-4" />
              <p className="text-gray-600 text-lg">Interactive heat stress map</p>
              <p className="text-gray-500 text-sm mt-2">Map visualization loading...</p>
            </div>
          </section>
        )}

        {/* Regions Tab */}
        {activeTab === 'regions' && (
          <section className="max-w-7xl mx-auto px-6 py-12">
            <h2 className="text-3xl font-light text-gray-900 mb-8">High-Heat Regions</h2>

            <div className="space-y-4">
              {regions.map((region) => (
                <div
                  key={region.id}
                  onClick={() => setSelectedRegion(region)}
                  className={`bg-white rounded-2xl p-6 border-2 cursor-pointer transition-all ${
                    selectedRegion?.id === region.id
                      ? 'border-yellow-600 bg-yellow-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900">{region.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">{region.trend}</p>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">HEAT RISK</p>
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-blue-400 to-yellow-500 to-red-600"
                            style={{ width: `${region.risk}%` }}
                          />
                        </div>
                        <p className="text-lg font-semibold text-yellow-600 w-12">{region.risk}</p>
                      </div>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">HEAT EVENTS</p>
                      <p className="text-3xl font-light text-gray-900">{region.events}</p>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">PEAK TEMP</p>
                      <p className="text-xl font-semibold text-red-600">
                        {region.temp}°C
                      </p>
                    </div>

                    <div className="text-right">
                      <ChevronRight className="text-gray-400 ml-auto" size={24} />
                    </div>
                  </div>

                  {selectedRegion?.id === region.id && (
                    <div className="mt-6 pt-6 border-t border-yellow-200">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Excess Mortality Risk</p>
                          <p className="text-2xl font-light text-red-600">+12%</p>
                          <p className="text-xs text-gray-500 mt-1">Estimated increase</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Heat Wave Duration</p>
                          <p className="text-2xl font-light">8 days</p>
                          <p className="text-xs text-gray-500 mt-1">Expected length</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Vulnerable Population</p>
                          <p className="text-2xl font-light text-yellow-600">2.4M</p>
                          <p className="text-xs text-gray-500 mt-1">Age 65+</p>
                        </div>
                      </div>
                      <button className="mt-6 w-full px-4 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg font-medium transition-colors">
                        View Health Response Plan →
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
            <h2 className="text-3xl font-light text-gray-900 mb-8">Heat Risk Analysis</h2>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              <div className="bg-white rounded-2xl border border-gray-200 p-8">
                <h3 className="text-xl font-semibold text-gray-900 mb-6">Regional Heat Hazard</h3>
                <div className="space-y-4">
                  <div>
                    <p className="text-sm text-gray-600 mb-2">Southern Mediterranean (Extreme)</p>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-5/5 h-full bg-red-600" />
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-2">Iberian Peninsula (Very High)</p>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-4/5 h-full bg-orange-500" />
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-2">Central Europe (Moderate)</p>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-3/5 h-full bg-yellow-500" />
                    </div>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600 mb-2">Northern Europe (Low)</p>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-2/5 h-full bg-green-500" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="bg-white rounded-2xl border border-gray-200 p-8">
                <h3 className="text-xl font-semibold text-gray-900 mb-6">Forecast Skill</h3>
                <div className="space-y-6">
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">7-day Heat Prediction</p>
                      <p className="text-sm font-semibold text-gray-900">85%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-85/100 h-full bg-green-600" />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">Temperature Forecast</p>
                      <p className="text-sm font-semibold text-gray-900">±1.5°C</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-4/5 h-full bg-green-600" />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">Health Impact Model</p>
                      <p className="text-sm font-semibold text-gray-900">68%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-68/100 h-full bg-blue-600" />
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
