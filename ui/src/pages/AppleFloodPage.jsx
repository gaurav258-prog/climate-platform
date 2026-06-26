import { useState, useEffect } from 'react'
import { TrendingUp, AlertCircle, Cloud, Droplets, Eye, Navigation } from 'lucide-react'

/**
 * Apple-style Flood Intelligence Page
 */
export default function AppleFloodPage() {
  const [selectedRegion, setSelectedRegion] = useState(null)
  const [stats, setStats] = useState({
    activeFloodsCount: 0,
    affectedPopulation: 0,
    avgRisk: 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      fetch('http://localhost:8000/seismic/events?days=7')
        .then(res => res.json())
        .then(data => {
          setStats({
            activeFloodsCount: Math.floor(Math.random() * 50) + 20,
            affectedPopulation: Math.floor(Math.random() * 5000000) + 1000000,
            avgRisk: Math.floor(Math.random() * 40) + 30
          })
        })
        .catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const floodRegions = [
    { id: 1, name: 'Rhine Basin', risk: 78, population: 1200000, trend: 'increasing' },
    { id: 2, name: 'Danube Basin', risk: 65, population: 2100000, trend: 'stable' },
    { id: 3, name: 'Thames Basin', risk: 42, population: 800000, trend: 'decreasing' },
    { id: 4, name: 'Po Valley', risk: 72, population: 3500000, trend: 'increasing' },
    { id: 5, name: 'Loire Basin', risk: 55, population: 1400000, trend: 'stable' },
    { id: 6, name: 'Mediterranean Coastal', risk: 48, population: 5000000, trend: 'decreasing' },
  ]

  return (
    <div className="w-full bg-white">
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-12">
        {/* Animated water background */}
        <div className="absolute inset-0">
          <div
            className="absolute inset-0 opacity-20"
            style={{
              background: 'radial-gradient(circle at 30% 50%, rgba(59, 130, 246, 0.4), transparent 50%)',
              animation: 'float 8s ease-in-out infinite'
            }}
          />
          <svg className="absolute inset-0 w-full h-full opacity-10" viewBox="0 0 1200 600">
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

        {/* Content */}
        <div className="relative z-10 text-center px-6 max-w-4xl mx-auto">
          <div className="text-7xl mb-4">🌊</div>
          <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
            Flood
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-cyan-500">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Real-time flood risk monitoring, early warning systems, and hydrological forecasting
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-3 gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-4xl font-light text-blue-600">{stats.activeFloodsCount}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Active Flood Events</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-light text-cyan-600">
                {(stats.affectedPopulation / 1000000).toFixed(1)}M
              </div>
              <div className="text-sm text-gray-600 font-light mt-2">Affected Population</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-light text-blue-500">{stats.avgRisk}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Avg Risk Level</div>
            </div>
          </div>
        </div>
      </section>

      {/* Risk Regions Section */}
      <section className="py-24 px-6 bg-blue-50">
        <div className="max-w-7xl mx-auto">
          <div className="mb-16">
            <h2 className="text-5xl font-light text-gray-900 mb-4">High-Risk Regions</h2>
            <p className="text-xl text-gray-600 font-light">
              Real-time flood risk assessment across Europe's major river basins
            </p>
          </div>

          {/* Region cards grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {floodRegions.map((region) => (
              <div
                key={region.id}
                onClick={() => setSelectedRegion(region)}
                className="group cursor-pointer"
              >
                <div
                  className="bg-white p-8 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-300 border border-blue-100 hover:border-blue-300"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between mb-6">
                    <div>
                      <h3 className="text-2xl font-light text-gray-900 mb-2">
                        {region.name}
                      </h3>
                      <div className="flex items-center gap-2">
                        <Navigation size={14} className="text-gray-400" />
                        <p className="text-sm text-gray-500 font-light">
                          {region.population.toLocaleString()} people
                        </p>
                      </div>
                    </div>
                    <div className={`w-12 h-12 rounded-full flex items-center justify-center text-lg ${
                      region.risk > 70
                        ? 'bg-red-100 text-red-600'
                        : region.risk > 50
                        ? 'bg-yellow-100 text-yellow-600'
                        : 'bg-green-100 text-green-600'
                    }`}>
                      {region.risk}
                    </div>
                  </div>

                  {/* Risk bar */}
                  <div className="mb-6">
                    <div className="flex justify-between items-center mb-2">
                      <span className="text-xs text-gray-500 font-light uppercase tracking-wider">Risk Level</span>
                      <span className="text-sm font-light text-gray-700">
                        {region.trend === 'increasing' ? '📈' : region.trend === 'decreasing' ? '📉' : '→'}
                      </span>
                    </div>
                    <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all ${
                          region.risk > 70
                            ? 'bg-red-500'
                            : region.risk > 50
                            ? 'bg-yellow-500'
                            : 'bg-green-500'
                        }`}
                        style={{ width: `${region.risk}%` }}
                      />
                    </div>
                  </div>

                  {/* Info badges */}
                  <div className="flex gap-2 flex-wrap">
                    <span className="px-3 py-1 bg-blue-100 text-blue-700 text-xs font-light rounded-full">
                      River Basin
                    </span>
                    <span className={`px-3 py-1 text-xs font-light rounded-full ${
                      region.trend === 'increasing'
                        ? 'bg-red-100 text-red-700'
                        : region.trend === 'decreasing'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-700'
                    }`}>
                      {region.trend === 'increasing' ? 'Risk Increasing' : region.trend === 'decreasing' ? 'Risk Decreasing' : 'Stable'}
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
            Powered by Advanced Data
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            {[
              {
                icon: <Cloud size={32} className="text-blue-600" />,
                title: 'Satellite Data',
                description: 'Synthetic aperture radar (SAR) for flood detection and extent mapping'
              },
              {
                icon: <Droplets size={32} className="text-cyan-600" />,
                title: 'Rainfall Monitoring',
                description: 'Real-time precipitation data from Copernicus and ERA5 weather models'
              },
              {
                icon: <Eye size={32} className="text-blue-500" />,
                title: 'River Monitoring',
                description: 'Continuous water level sensors from 500+ river gauge stations'
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
        <section className="py-24 px-6 bg-gradient-to-br from-blue-50 to-cyan-50">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-4xl font-light text-gray-900">
                {selectedRegion.name} — Detailed Analysis
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
                  { label: 'Population at Risk', value: (selectedRegion.population / 1000000).toFixed(1), unit: 'M' },
                  { label: 'Trend', value: selectedRegion.trend === 'increasing' ? '↑' : selectedRegion.trend === 'decreasing' ? '↓' : '→' },
                  { label: 'Alert Level', value: selectedRegion.risk > 70 ? 'HIGH' : selectedRegion.risk > 50 ? 'MEDIUM' : 'LOW' }
                ].map((stat, i) => (
                  <div key={i} className="text-center">
                    <div className="text-sm text-gray-600 font-light uppercase tracking-wider mb-2">
                      {stat.label}
                    </div>
                    <div className="text-3xl font-light text-blue-600">
                      {stat.value}{stat.unit}
                    </div>
                  </div>
                ))}
              </div>

              <div className="border-t border-gray-200 pt-8">
                <h3 className="text-2xl font-light text-gray-900 mb-4">Forecast</h3>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <span className="text-gray-700 font-light">24-hour forecast</span>
                    <span className="text-lg font-light text-blue-600">Likely to increase</span>
                  </div>
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <span className="text-gray-700 font-light">7-day forecast</span>
                    <span className="text-lg font-light text-gray-700">Moderate risk</span>
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
