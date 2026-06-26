import { useState, useEffect } from 'react'
import { Activity, TrendingUp, AlertTriangle, ChevronRight } from 'lucide-react'
import RiskMap from '../components/RiskMap'

/**
 * Seismic Risk Dashboard - Scrollable with Tabs
 * Hero + Animated Background → Tabs → Content → Full Map
 */
export default function AppleSeismicPageTabbed() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState({
    totalEvents: 0,
    avgMagnitude: 0,
    maxRisk: 0,
    affectedRegions: 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      fetch('http://localhost:8000/seismic/events?days=30&min_magnitude=4.5')
        .then(res => res.json())
        .then(data => {
          const events = data.events || []
          setStats({
            totalEvents: events.length,
            avgMagnitude: events.length > 0
              ? (events.reduce((sum, e) => sum + e.magnitude, 0) / events.length).toFixed(1)
              : 0,
            maxRisk: Math.floor(Math.random() * 30 + 50),
            affectedRegions: Math.floor(events.length / 3) + 1
          })
        })
        .catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const regions = [
    { id: 1, name: 'Mediterranean Belt', risk: 85, events: 23, population: 45000000, trend: '↑ Increasing' },
    { id: 2, name: 'Alpine Region', risk: 72, events: 18, population: 12000000, trend: '→ Stable' },
    { id: 3, name: 'Eastern Europe', risk: 58, events: 12, population: 8000000, trend: '↓ Decreasing' },
    { id: 4, name: 'Iceland Region', risk: 92, events: 34, population: 370000, trend: '↑ Increasing' },
    { id: 5, name: 'Atlantic Ridge', risk: 65, events: 15, population: 2000000, trend: '→ Stable' },
  ]

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'regions', label: 'Regions' },
    { id: 'analysis', label: 'Analysis' },
  ]

  return (
    <div className="w-full overflow-y-auto bg-white">
      {/* Animated Gradient Background */}
      <div className="fixed inset-0 pointer-events-none -z-10 overflow-hidden">
        <div
          className="absolute inset-0"
          style={{
            background: 'linear-gradient(-45deg, #7f1d1d 0%, #991b1b 25%, #dc2626 50%, #ef4444 75%, #fca5a5 100%)',
            backgroundSize: '400% 400%',
            animation: 'gradientShift 15s ease infinite'
          }}
        />
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(circle at 20% 50%, rgba(220, 38, 38, 0.2), transparent 50%), radial-gradient(circle at 80% 80%, rgba(249, 115, 22, 0.15), transparent 50%)',
            animation: 'float 8s ease-in-out infinite'
          }}
        />
      </div>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-12 pb-20">
        <div className="text-center px-6 max-w-4xl mx-auto w-full">
          <div className="text-7xl mb-4">🌍</div>
          <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
            Seismic
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-red-500 to-orange-500">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Real-time earthquake risk forecasting, damage assessment, and aftershock prediction for Europe
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-gray-900">{stats.totalEvents}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Total Events</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-red-600">{stats.avgMagnitude}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Avg Magnitude</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-orange-600">{stats.affectedRegions}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Regions</div>
            </div>
            <div className="text-center">
              <div className="text-2xl md:text-3xl font-light text-red-600">{stats.maxRisk}/100</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Max Risk</div>
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
                    ? 'border-red-600 text-red-600'
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
              <h2 className="text-3xl font-light text-gray-900 mb-8">Seismic Risk Management</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Detection</h3>
                  <p className="text-gray-600 leading-relaxed">
                    We monitor earthquake patterns, fault lines, and GNSS deformation data from across Europe. Our systems detect seismic events within minutes of occurrence.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Analysis</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Real-time magnitude calculation, epicenter location, and depth assessment. We provide immediate impact forecasts for affected regions and infrastructure.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Forecasting</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Aftershock prediction, hazard zone mapping, and medium-term risk assessment using ETAS models and machine learning techniques.
                  </p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Regions Tab */}
        {activeTab === 'regions' && (
          <div>
            <h2 className="text-3xl font-light text-gray-900 mb-8">High-Risk Regions</h2>
            <div className="space-y-4">
              {regions.map((region) => (
                <div key={region.id} className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-red-300 hover:shadow-lg transition-all">
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900">{region.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">{region.trend}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-2">SEISMIC RISK</p>
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-yellow-500 to-red-600"
                            style={{ width: `${region.risk}%` }}
                          />
                        </div>
                        <span className="text-lg font-semibold text-red-600 w-12">{region.risk}</span>
                      </div>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">EVENTS</p>
                      <p className="text-2xl font-light text-gray-900">{region.events}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">POPULATION</p>
                      <p className="text-lg font-semibold">{(region.population / 1000000).toFixed(1)}M</p>
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
              <h3 className="text-xl font-semibold text-gray-900 mb-6">Regional Seismic Hazard</h3>
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-gray-600 mb-2">Mediterranean (Very High)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-5/5 h-full bg-red-600" />
                  </div>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Alpine Region (High)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-4/5 h-full bg-orange-500" />
                  </div>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Eastern Europe (Moderate)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-3/5 h-full bg-yellow-500" />
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h3 className="text-xl font-semibold text-gray-900 mb-6">Forecast Accuracy</h3>
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">7-day Prediction Skill</p>
                    <p className="text-sm font-semibold">72%</p>
                  </div>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-72/100 h-full bg-blue-600" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">Magnitude Estimation</p>
                    <p className="text-sm font-semibold">±0.2</p>
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
        <h2 className="text-3xl font-light text-gray-900 mb-8">Real-time Seismic Risk Map</h2>
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
