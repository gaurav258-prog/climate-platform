import { useState, useEffect } from 'react'
import { Flame, TrendingUp, AlertTriangle, Activity, ChevronRight } from 'lucide-react'

/**
 * Tabbed Wildfire Risk Dashboard
 * - Animated fire background
 * - Clickable tab navigation
 * - Map view with danger zones
 * - Risk analysis by region
 */
export default function AppleWildfirePageTabbed() {
  const [activeTab, setActiveTab] = useState('overview')
  const [stats, setStats] = useState({
    activeWildfires: 0,
    affectedRegions: 0,
    avgRisk: 0,
    areaAtRisk: 0
  })
  const [selectedRegion, setSelectedRegion] = useState(null)

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
    { id: 'overview', label: 'Overview', icon: Activity },
    { id: 'map', label: 'Fire Map', icon: Flame },
    { id: 'regions', label: 'Regions', icon: AlertTriangle },
    { id: 'analysis', label: 'Analysis', icon: TrendingUp },
  ]

  return (
    <div className="w-full h-full overflow-y-auto bg-white">
      {/* Animated Fire Background */}
      <div className="fixed inset-0 pointer-events-none">
        <div
          className="absolute inset-0"
          style={{
            background: 'radial-gradient(circle at 20% 50%, rgba(249, 115, 22, 0.08), transparent 50%), radial-gradient(circle at 80% 80%, rgba(239, 68, 68, 0.06), transparent 50%)',
            animation: 'float 12s ease-in-out infinite'
          }}
        />
        {/* Fire wave pattern */}
        <svg className="absolute inset-0 w-full h-full opacity-5" viewBox="0 0 1200 600">
          <defs>
            <pattern id="fire" patternUnits="userSpaceOnUse" width="100" height="100">
              <path
                d="M0,50 Q25,35 50,50 T100,50"
                stroke="#f97316"
                strokeWidth="2"
                fill="none"
                opacity="0.3"
              />
            </pattern>
          </defs>
          <rect width="1200" height="600" fill="url(#fire)" />
        </svg>
      </div>

      {/* Main Content */}
      <div className="relative z-10 w-full">
        {/* Header */}
        <header className="sticky top-0 z-50 bg-white/95 backdrop-blur border-b border-gray-200">
          <div className="max-w-7xl mx-auto px-6 py-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h1 className="text-3xl font-light text-gray-900">🔥 Wildfire Intelligence</h1>
                <p className="text-sm text-gray-600 mt-1">Predictive wildfire risk mapping with satellite data</p>
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
                        ? 'border-orange-600 text-orange-600'
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
                    <p className="text-sm text-gray-600 font-medium mb-1">ACTIVE FIRES</p>
                    <p className="text-4xl font-light text-gray-900">{stats.activeWildfires}</p>
                    <p className="text-xs text-gray-500 mt-2">Current incidents</p>
                  </div>
                  <Activity className="text-orange-600" size={24} />
                </div>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-1">AT-RISK REGIONS</p>
                    <p className="text-4xl font-light text-gray-900">{stats.affectedRegions}</p>
                    <p className="text-xs text-gray-500 mt-2">High hazard zones</p>
                  </div>
                  <Flame className="text-red-600" size={24} />
                </div>
              </div>

              <div className="bg-white rounded-2xl p-6 border border-gray-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-gray-600 font-medium mb-1">AVG RISK LEVEL</p>
                    <p className="text-4xl font-light text-gray-900">{stats.avgRisk}/100</p>
                    <p className="text-xs text-gray-500 mt-2">Regional average</p>
                  </div>
                  <TrendingUp className="text-orange-600" size={24} />
                </div>
              </div>

              <div className="bg-gradient-to-br from-orange-50 to-red-50 rounded-2xl p-6 border border-orange-200">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-sm text-orange-600 font-medium mb-1">AREA AT RISK</p>
                    <p className="text-3xl font-light text-orange-600">
                      {(stats.areaAtRisk / 1000).toFixed(0)}k km²
                    </p>
                    <p className="text-xs text-orange-500 mt-2">Forest area</p>
                  </div>
                  <AlertTriangle className="text-orange-600" size={24} />
                </div>
              </div>
            </div>

            <div className="bg-white rounded-2xl border border-gray-200 p-8">
              <h2 className="text-2xl font-light text-gray-900 mb-6">Wildfire Risk Management</h2>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Detection</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Satellite thermal imaging detects fires within minutes. Real-time MODIS and Sentinel-5 data provide immediate fire location and intensity assessment.
                  </p>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Prediction</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Weather-driven fire spread modeling using wind speed, temperature, humidity, and fuel moisture. Predicts fire direction and expansion rate.
                  </p>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 mb-3">Response</h3>
                  <p className="text-gray-600 leading-relaxed">
                    Automatic alerts to fire services, evacuation zone mapping, and resource deployment recommendations. Real-time smoke impact forecasting.
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
              <Flame size={64} className="mx-auto text-orange-300 mb-4" />
              <p className="text-gray-600 text-lg">Interactive wildfire risk map</p>
              <p className="text-gray-500 text-sm mt-2">Map visualization loading...</p>
            </div>
          </section>
        )}

        {/* Regions Tab */}
        {activeTab === 'regions' && (
          <section className="max-w-7xl mx-auto px-6 py-12">
            <h2 className="text-3xl font-light text-gray-900 mb-8">High-Risk Regions</h2>

            <div className="space-y-4">
              {regions.map((region) => (
                <div
                  key={region.id}
                  onClick={() => setSelectedRegion(region)}
                  className={`bg-white rounded-2xl p-6 border-2 cursor-pointer transition-all ${
                    selectedRegion?.id === region.id
                      ? 'border-orange-600 bg-orange-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center">
                    <div>
                      <h3 className="text-xl font-semibold text-gray-900">{region.name}</h3>
                      <p className="text-sm text-gray-600 mt-1">{region.trend}</p>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">FIRE RISK</p>
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-40 h-2 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-yellow-500 to-red-600"
                            style={{ width: `${region.risk}%` }}
                          />
                        </div>
                        <p className="text-lg font-semibold text-red-600 w-12">{region.risk}</p>
                      </div>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">FIRES</p>
                      <p className="text-3xl font-light text-gray-900">{region.fires}</p>
                    </div>

                    <div className="text-center">
                      <p className="text-sm text-gray-600 mb-1">AREA AT RISK</p>
                      <p className="text-xl font-semibold text-gray-900">
                        {(region.area / 1000).toFixed(0)}k km²
                      </p>
                    </div>

                    <div className="text-right">
                      <ChevronRight className="text-gray-400 ml-auto" size={24} />
                    </div>
                  </div>

                  {selectedRegion?.id === region.id && (
                    <div className="mt-6 pt-6 border-t border-orange-200">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Burnt Area (YTD)</p>
                          <p className="text-2xl font-light text-red-600">156,000 ha</p>
                          <p className="text-xs text-gray-500 mt-1">This year total</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Fire Weather Index</p>
                          <p className="text-2xl font-light text-orange-600">82/100</p>
                          <p className="text-xs text-gray-500 mt-1">Very high risk</p>
                        </div>
                        <div>
                          <p className="text-sm text-gray-600 font-medium mb-2">Fuel Moisture</p>
                          <p className="text-2xl font-light">12%</p>
                          <p className="text-xs text-gray-500 mt-1">Critical low</p>
                        </div>
                      </div>
                      <button className="mt-6 w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors">
                        View Fire Spread Model →
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
            <h2 className="text-3xl font-light text-gray-900 mb-8">Wildfire Risk Analysis</h2>

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
                  <div>
                    <p className="text-sm text-gray-600 mb-2">Central Europe (Moderate)</p>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-2/5 h-full bg-green-500" />
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
                      <p className="text-sm font-semibold text-gray-900">96%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-96/100 h-full bg-green-600" />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">Spread Prediction (24h)</p>
                      <p className="text-sm font-semibold text-gray-900">±20%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-3/5 h-full bg-blue-600" />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between mb-2">
                      <p className="text-sm text-gray-600">Smoke Impact Forecast</p>
                      <p className="text-sm font-semibold text-gray-900">72%</p>
                    </div>
                    <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                      <div className="w-72/100 h-full bg-blue-600" />
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
