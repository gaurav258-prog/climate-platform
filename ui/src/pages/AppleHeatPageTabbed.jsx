import { useState, useEffect } from 'react'
import { Thermometer, TrendingUp, AlertTriangle, ChevronRight } from 'lucide-react'
import RiskMap from '../components/RiskMap'

/**
 * Heat Stress Risk Dashboard - Scrollable with Tabs
 * Hero + Animated Background → Tabs → Content → Full Map
 */
export default function AppleHeatPageTabbed() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState({
    extremeHeatEvents: 0,
    affectedRegions: 0,
    avgRisk: 0,
    populationAtRisk: 0
  })

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
    { id: 'overview', label: 'Overview' },
    { id: 'regions', label: 'Regions' },
    { id: 'analysis', label: 'Analysis' },
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-white">
      {/* Animated Gradient Background */}
      <div className="fixed inset-0 pointer-events-none -z-10 bg-gradient-to-br from-yellow-900 via-yellow-700 to-orange-500" />
      <div className="fixed inset-0 pointer-events-none -z-10">
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(circle at 20% 50%, rgba(251, 191, 36, 0.3), transparent 50%), radial-gradient(circle at 80% 80%, rgba(249, 115, 22, 0.2), transparent 50%)',
            animation: 'float 8s ease-in-out infinite'
          }}
        />
      </div>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-12 pb-20">
        <div className="text-center px-6 max-w-4xl mx-auto w-full">
          <div className="text-7xl mb-4">☀️</div>
          <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
            Heat Stress
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-yellow-500 to-orange-600">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Monitor extreme heat events, forecast health impacts, and coordinate emergency response for vulnerable populations
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-yellow-600">{stats.extremeHeatEvents}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Heat Waves</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-orange-600">{stats.affectedRegions}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Regions</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-yellow-500">{stats.avgRisk}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Avg Risk</div>
            </div>
            <div className="text-center">
              <div className="text-2xl md:text-3xl font-light text-yellow-600">
                {(stats.populationAtRisk / 1000000).toFixed(0)}M
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
                    ? 'border-yellow-600 text-yellow-600'
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
              <h2 className="text-3xl font-light text-gray-900 mb-8">Heat Stress Monitoring</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Detection</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Real-time temperature monitoring from weather stations and satellites. Heat wave identification based on temperature anomalies and duration thresholds.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Health Impact</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Estimate excess mortality risk based on temperature, humidity, and vulnerable population distribution. Calculate strain on healthcare systems.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Response</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Automated alerts to public health agencies and vulnerable groups. Cool center location recommendations and medical resource allocation.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Regions Tab */}
        {activeTab === 'regions' && (
          <div>
            <h2 className="text-3xl font-light text-gray-900 mb-8">High-Heat Regions</h2>
            <div className="space-y-4">
              {regions.map((region) => (
                <div key={region.id} className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-yellow-300 hover:shadow-lg transition-all">
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900">{region.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">{region.trend}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-2">HEAT RISK</p>
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-blue-400 to-yellow-500 to-red-600"
                            style={{ width: `${region.risk}%` }}
                          />
                        </div>
                        <span className="text-lg font-semibold text-yellow-600 w-12">{region.risk}</span>
                      </div>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">EVENTS</p>
                      <p className="text-2xl font-light text-gray-900">{region.events}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">PEAK TEMP</p>
                      <p className="text-lg font-semibold text-red-600">{region.temp}°C</p>
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
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h3 className="text-xl font-semibold text-gray-900 mb-6">Forecast Skill</h3>
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">7-day Heat Prediction</p>
                    <p className="text-sm font-semibold">85%</p>
                  </div>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-85/100 h-full bg-green-600" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">Temperature Forecast</p>
                    <p className="text-sm font-semibold">±1.5°C</p>
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
        <h2 className="text-3xl font-light text-gray-900 mb-8">Real-time Heat Risk Map</h2>
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
