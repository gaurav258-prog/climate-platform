import { useState, useEffect } from 'react'
import { Flame, TrendingUp, AlertTriangle, ChevronRight } from 'lucide-react'
import RiskMap from '../components/RiskMap'

/**
 * Wildfire Risk Dashboard - Scrollable with Tabs
 * Hero + Animated Background → Tabs → Content → Full Map
 */
export default function AppleWildfirePageTabbed() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState({
    activeWildfires: 0,
    affectedRegions: 0,
    avgRisk: 0,
    areaAtRisk: 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      setStats({
        activeWildfires: Math.floor(Math.random() * 80) + 40,
        affectedRegions: Math.floor(Math.random() * 20) + 10,
        avgRisk: Math.floor(Math.random() * 50) + 50,
        areaAtRisk: Math.floor(Math.random() * 8000) + 2000
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const regions = [
    { id: 1, name: 'Mediterranean Basin', risk: 92, fires: 45, area: 850000, trend: '↑ Increasing' },
    { id: 2, name: 'Iberian Peninsula', risk: 85, fires: 38, area: 650000, trend: '↑ Increasing' },
    { id: 3, name: 'Central Europe', risk: 58, fires: 18, area: 280000, trend: '→ Stable' },
    { id: 4, name: 'Balkans', risk: 72, fires: 28, area: 420000, trend: '↑ Increasing' },
    { id: 5, name: 'France & Alps', risk: 65, fires: 22, area: 350000, trend: '→ Stable' },
  ]

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'regions', label: 'Regions' },
    { id: 'analysis', label: 'Analysis' },
  ]

  return (
    <div className="w-full overflow-y-auto bg-transparent relative">
      {/* Animated Gradient Background */}
      <div className="fixed inset-0 pointer-events-none -z-10 bg-gradient-to-br from-orange-900 via-orange-700 to-red-500" />
      <div className="fixed inset-0 pointer-events-none -z-10">
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(circle at 20% 50%, rgba(249, 115, 22, 0.3), transparent 50%), radial-gradient(circle at 80% 80%, rgba(239, 68, 68, 0.2), transparent 50%)',
            animation: 'float 8s ease-in-out infinite'
          }}
        />
      </div>

      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-12 pb-20">
        <div className="text-center px-6 max-w-4xl mx-auto w-full">
          <div className="text-7xl mb-4">🔥</div>
          <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
            Wildfire
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-orange-500 to-red-600">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Predictive wildfire risk mapping with satellite data, fire spread modeling, and emergency response coordination
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-orange-600">{stats.activeWildfires}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Active Fires</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-red-600">{stats.affectedRegions}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Regions</div>
            </div>
            <div className="text-center">
              <div className="text-3xl md:text-4xl font-light text-orange-500">{stats.avgRisk}</div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Avg Risk</div>
            </div>
            <div className="text-center">
              <div className="text-2xl md:text-3xl font-light text-red-600">
                {(stats.areaAtRisk / 1000).toFixed(0)}k km²
              </div>
              <div className="text-xs md:text-sm text-gray-600 font-light mt-2">Area at Risk</div>
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
                    ? 'border-orange-600 text-orange-600'
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
              <h2 className="text-3xl font-light text-gray-900 mb-8">Wildfire Risk Management</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Detection</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Satellite thermal imaging detects fires within minutes. Real-time MODIS and Sentinel-5 data provide immediate fire location and intensity assessment.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Prediction</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Weather-driven fire spread modeling using wind speed, temperature, humidity, and fuel moisture. Predicts fire direction and expansion rate.
                  </p>
                </div>
                <div className="bg-white rounded-2xl border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Response</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Automatic alerts to fire services, evacuation zone mapping, and resource deployment recommendations. Real-time smoke impact forecasting.
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
                <div key={region.id} className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-orange-300 hover:shadow-lg transition-all">
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900">{region.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">{region.trend}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-2">FIRE RISK</p>
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
                      <p className="text-sm text-gray-600 mb-1">FIRES</p>
                      <p className="text-2xl font-light text-gray-900">{region.fires}</p>
                    </div>
                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">AREA AT RISK</p>
                      <p className="text-lg font-semibold">{(region.area / 1000).toFixed(0)}k km²</p>
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
              <h3 className="text-xl font-semibold text-gray-900 mb-6">Regional Hazard</h3>
              <div className="space-y-4">
                <div>
                  <p className="text-sm text-gray-600 mb-2">Mediterranean (Extreme)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-5/5 h-full bg-red-600" />
                  </div>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Iberian (Very High)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-4/5 h-full bg-orange-500" />
                  </div>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-2">Balkans (High)</p>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-3/5 h-full bg-yellow-500" />
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h3 className="text-xl font-semibold text-gray-900 mb-6">Detection Accuracy</h3>
              <div className="space-y-6">
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">Fire Detection Rate</p>
                    <p className="text-sm font-semibold">96%</p>
                  </div>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-96/100 h-full bg-green-600" />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between mb-2">
                    <p className="text-sm text-gray-600">Spread Prediction (24h)</p>
                    <p className="text-sm font-semibold">±20%</p>
                  </div>
                  <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div className="w-3/5 h-full bg-blue-600" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Full Map Section - Always Visible */}
      <section className="py-20 px-6 max-w-7xl mx-auto w-full">
        <h2 className="text-3xl font-light text-gray-900 mb-8">Real-time Wildfire Risk Map</h2>
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
