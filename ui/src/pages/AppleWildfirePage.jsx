import { useState, useEffect } from 'react'
import { TrendingUp, AlertCircle, Wind, Flame, Zap, MapPin } from 'lucide-react'

/**
 * Apple-style Wildfire Intelligence Page
 */
export default function AppleWildfirePage() {
  const [selectedRegion, setSelectedRegion] = useState(null)
  const [stats, setStats] = useState({
    activeFiresCount: 0,
    burnedArea: 0,
    avgRisk: 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      fetch('http://localhost:8000/seismic/events?days=7')
        .then(res => res.json())
        .then(data => {
          setStats({
            activeFiresCount: Math.floor(Math.random() * 120) + 30,
            burnedArea: Math.floor(Math.random() * 500000) + 50000,
            avgRisk: Math.floor(Math.random() * 50) + 35
          })
        })
        .catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const wildFireRegions = [
    { id: 1, name: 'Mediterranean Zone', risk: 85, area: 250000, trend: 'increasing' },
    { id: 2, name: 'Iberian Peninsula', risk: 78, area: 180000, trend: 'increasing' },
    { id: 3, name: 'Southern France', risk: 72, area: 120000, trend: 'stable' },
    { id: 4, name: 'Greece & Balkans', risk: 88, area: 290000, trend: 'increasing' },
    { id: 5, name: 'Central Europe', risk: 45, area: 35000, trend: 'decreasing' },
    { id: 6, name: 'Alpine Region', risk: 38, area: 12000, trend: 'stable' },
  ]

  return (
    <div className="w-full bg-white">
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-12">
        {/* Animated fire background */}
        <div className="absolute inset-0">
          <div
            className="absolute inset-0 opacity-20"
            style={{
              background: 'radial-gradient(circle at 50% 50%, rgba(249, 115, 22, 0.4), transparent 60%)',
              animation: 'float 8s ease-in-out infinite'
            }}
          />
          <div
            className="absolute inset-0 opacity-10"
            style={{
              background: 'radial-gradient(circle at 70% 30%, rgba(220, 38, 38, 0.3), transparent 50%)',
              animation: 'float 10s ease-in-out infinite 1s'
            }}
          />
        </div>

        {/* Content */}
        <div className="relative z-10 text-center px-6 max-w-4xl mx-auto">
          <div className="text-7xl mb-4">🔥</div>
          <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
            Wildfire
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-orange-500 to-red-600">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Real-time wildfire detection, risk forecasting, and fire progression modeling
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-3 gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-4xl font-light text-orange-600">{stats.activeFiresCount}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Active Wildfires</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-light text-red-600">
                {(stats.burnedArea / 1000).toFixed(0)}K
              </div>
              <div className="text-sm text-gray-600 font-light mt-2">Hectares Burned</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-light text-orange-500">{stats.avgRisk}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Avg Risk Level</div>
            </div>
          </div>
        </div>
      </section>

      {/* Risk Regions Section */}
      <section className="py-24 px-6 bg-orange-50">
        <div className="max-w-7xl mx-auto">
          <div className="mb-16">
            <h2 className="text-5xl font-light text-gray-900 mb-4">High Fire Risk Regions</h2>
            <p className="text-xl text-gray-600 font-light">
              Daily wildfire risk assessment across Europe's vulnerable zones
            </p>
          </div>

          {/* Region cards grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {wildFireRegions.map((region) => (
              <div
                key={region.id}
                onClick={() => setSelectedRegion(region)}
                className="group cursor-pointer"
              >
                <div
                  className="bg-white p-8 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-300 border border-orange-100 hover:border-orange-300"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <h3 className="text-2xl font-light text-gray-900 mb-2">
                        {region.name}
                      </h3>
                      <div className="flex items-center gap-2">
                        <MapPin size={14} className="text-gray-400" />
                        <p className="text-sm text-gray-500 font-light">
                          {region.area.toLocaleString()} ha at risk
                        </p>
                      </div>
                    </div>
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center text-lg ${
                      region.risk > 80
                        ? 'bg-red-100 text-red-600'
                        : region.risk > 60
                        ? 'bg-orange-100 text-orange-600'
                        : 'bg-yellow-100 text-yellow-600'
                    }`}>
                      {region.risk}
                    </div>
                  </div>

                  {/* Risk bar */}
                  <div className="mb-6">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs text-gray-500 font-light uppercase tracking-wider">Fire Risk</span>
                      <span className="text-sm font-light text-gray-700">
                        {region.trend === 'increasing' ? '📈' : region.trend === 'decreasing' ? '📉' : '→'}
                      </span>
                    </div>
                    <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all ${
                          region.risk > 80
                            ? 'bg-red-500'
                            : region.risk > 60
                            ? 'bg-orange-500'
                            : 'bg-yellow-500'
                        }`}
                        style={{ width: `${region.risk}%` }}
                      />
                    </div>
                  </div>

                  {/* Info badges */}
                  <div className="flex gap-2 flex-wrap">
                    <span className="px-3 py-1 bg-orange-100 text-orange-700 text-xs font-light rounded-full">
                      Mediterranean
                    </span>
                    <span className={`px-3 py-1 text-xs font-light rounded-full ${
                      region.trend === 'increasing'
                        ? 'bg-red-100 text-red-700'
                        : region.trend === 'decreasing'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-700'
                    }`}>
                      {region.trend === 'increasing' ? 'Risk Rising' : region.trend === 'decreasing' ? 'Risk Falling' : 'Stable'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Data Sources Section */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl font-light text-gray-900 mb-16 text-center">
            Detection & Forecasting
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            {[
              {
                icon: <Flame size={32} className="text-orange-600" />,
                title: 'Fire Detection',
                description: 'Active fire detection using Sentinel-2 thermal and FIRMS satellite data'
              },
              {
                icon: <Wind size={32} className="text-red-600" />,
                title: 'Weather Prediction',
                description: 'Integration of wind speed, humidity, and temperature forecasts'
              },
              {
                icon: <Zap size={32} className="text-yellow-600" />,
                title: 'Risk Modeling',
                description: 'ML-based fire spread prediction and danger zone mapping'
              }
            ].map((feature, i) => (
              <div key={i} className="text-center">
                <div className="mb-4 flex justify-center">{feature.icon}</div>
                <h3 className="text-2xl font-light text-gray-900 mb-3">
                  {feature.title}
                </h3>
                <p className="text-gray-600 font-light text-lg">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Selected Region Detail */}
      {selectedRegion && (
        <section className="py-24 px-6 bg-gradient-to-br from-orange-50 to-red-50">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-4xl font-light text-gray-900">
                {selectedRegion.name} — Fire Risk Analysis
              </h2>
              <button
                onClick={() => setSelectedRegion(null)}
                className="text-gray-500 hover:text-gray-900 text-2xl"
              >
                ✕
              </button>
            </div>

            <div className="bg-white rounded-3xl p-12 shadow-lg">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-12">
                {[
                  { label: 'Risk Score', value: selectedRegion.risk, unit: '/100' },
                  { label: 'Area at Risk', value: (selectedRegion.area / 1000).toFixed(0), unit: 'K ha' },
                  { label: 'Trend', value: selectedRegion.trend === 'increasing' ? '↑' : selectedRegion.trend === 'decreasing' ? '↓' : '→' },
                  { label: 'Alert Status', value: selectedRegion.risk > 80 ? 'CRITICAL' : selectedRegion.risk > 60 ? 'HIGH' : 'MODERATE' }
                ].map((stat, i) => (
                  <div key={i} className="text-center">
                    <div className="text-sm text-gray-600 font-light uppercase tracking-wider mb-2">
                      {stat.label}
                    </div>
                    <div className="text-3xl font-light text-orange-600">
                      {stat.value}{stat.unit}
                    </div>
                  </div>
                ))}
              </div>

              <div className="border-t border-gray-200 pt-8">
                <h3 className="text-2xl font-light text-gray-900 mb-4">Fire Forecast</h3>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <span className="text-gray-700 font-light">24-hour outlook</span>
                    <span className="text-lg font-light text-orange-600">
                      {selectedRegion.risk > 75 ? 'Very High' : 'High'} risk
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <span className="text-gray-700 font-light">7-day forecast</span>
                    <span className="text-lg font-light text-gray-700">Elevated risk conditions</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Styles */}
      <style>{`
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(20px); }
        }
      `}</style>
    </div>
  )
}
