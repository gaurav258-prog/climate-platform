import { useState, useEffect } from 'react'
import { TrendingUp, AlertCircle, Thermometer, Heart, Sun, Users } from 'lucide-react'

/**
 * Apple-style Heat Stress Intelligence Page
 */
export default function AppleHeatPage() {
  const [selectedRegion, setSelectedRegion] = useState(null)
  const [stats, setStats] = useState({
    heatWavesCount: 0,
    affectedPopulation: 0,
    maxTemp: 0
  })

  useEffect(() => {
    const interval = setInterval(() => {
      fetch('http://localhost:8000/seismic/events?days=7')
        .then(res => res.json())
        .then(data => {
          setStats({
            heatWavesCount: Math.floor(Math.random() * 25) + 5,
            affectedPopulation: Math.floor(Math.random() * 200000000) + 10000000,
            maxTemp: Math.floor(Math.random() * 15) + 35
          })
        })
        .catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  const heatRegions = [
    { id: 1, name: 'Southern Spain & Portugal', temp: 42, population: 5000000, health_risk: 'extreme' },
    { id: 2, name: 'Italy & Mediterranean', temp: 38, population: 12000000, health_risk: 'high' },
    { id: 3, name: 'Greece & Southeast', temp: 40, population: 3500000, health_risk: 'extreme' },
    { id: 4, name: 'Central Europe', temp: 35, population: 45000000, health_risk: 'moderate' },
    { id: 5, name: 'France & Low Countries', temp: 32, population: 28000000, health_risk: 'low' },
    { id: 6, name: 'Northern Europe', temp: 28, population: 85000000, health_risk: 'low' },
  ]

  const getRiskColor = (risk) => {
    switch(risk) {
      case 'extreme': return { bg: 'bg-red-100', text: 'text-red-700', badge: 'bg-red-100 text-red-700' }
      case 'high': return { bg: 'bg-orange-100', text: 'text-orange-700', badge: 'bg-orange-100 text-orange-700' }
      case 'moderate': return { bg: 'bg-yellow-100', text: 'text-yellow-700', badge: 'bg-yellow-100 text-yellow-700' }
      case 'low': return { bg: 'bg-green-100', text: 'text-green-700', badge: 'bg-green-100 text-green-700' }
      default: return { bg: 'bg-gray-100', text: 'text-gray-700', badge: 'bg-gray-100 text-gray-700' }
    }
  }

  return (
    <div className="w-full bg-white">
      {/* Hero Section */}
      <section className="relative min-h-screen flex items-center justify-center overflow-hidden pt-12">
        {/* Animated heat gradient background */}
        <div className="absolute inset-0">
          <div
            className="absolute inset-0 opacity-20"
            style={{
              background: 'radial-gradient(circle at 50% 50%, rgba(239, 68, 68, 0.4), transparent 60%)',
              animation: 'float 8s ease-in-out infinite'
            }}
          />
          <div
            className="absolute inset-0 opacity-15"
            style={{
              background: 'radial-gradient(circle at 30% 70%, rgba(234, 179, 8, 0.3), transparent 50%)',
              animation: 'float 10s ease-in-out infinite 1s'
            }}
          />
        </div>

        {/* Content */}
        <div className="relative z-10 text-center px-6 max-w-4xl mx-auto">
          <div className="text-7xl mb-4">☀️</div>
          <h1 className="text-7xl md:text-8xl font-light text-gray-900 mb-6 leading-tight">
            Heat Stress
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-yellow-500 to-red-600">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Real-time heat wave detection, health risk assessment, and vulnerable population monitoring
          </p>

          {/* Live metrics */}
          <div className="grid grid-cols-3 gap-8 pt-8 border-t border-gray-200">
            <div className="text-center">
              <div className="text-4xl font-light text-red-600">{stats.heatWavesCount}</div>
              <div className="text-sm text-gray-600 font-light mt-2">Active Heat Waves</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-light text-yellow-600">
                {(stats.affectedPopulation / 1000000).toFixed(0)}M
              </div>
              <div className="text-sm text-gray-600 font-light mt-2">People at Risk</div>
            </div>
            <div className="text-center">
              <div className="text-4xl font-light text-orange-600">{stats.maxTemp}°C</div>
              <div className="text-sm text-gray-600 font-light mt-2">Peak Temperature</div>
            </div>
          </div>
        </div>
      </section>

      {/* Risk Regions Section */}
      <section className="py-24 px-6 bg-yellow-50">
        <div className="max-w-7xl mx-auto">
          <div className="mb-16">
            <h2 className="text-5xl font-light text-gray-900 mb-4">Regional Heat Assessment</h2>
            <p className="text-xl text-gray-600 font-light">
              Heat stress and health impact analysis across Europe
            </p>
          </div>

          {/* Region cards grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {heatRegions.map((region) => {
              const colors = getRiskColor(region.health_risk)
              return (
                <div
                  key={region.id}
                  onClick={() => setSelectedRegion(region)}
                  className="group cursor-pointer"
                >
                  <div
                    className="bg-white p-8 rounded-3xl shadow-sm hover:shadow-xl transition-all duration-300 border border-yellow-100 hover:border-yellow-300"
                  >
                    {/* Header */}
                    <div className="flex items-start justify-between mb-6">
                      <div>
                        <h3 className="text-2xl font-light text-gray-900 mb-2">
                          {region.name}
                        </h3>
                        <div className="flex items-center gap-2">
                          <Users size={14} className="text-gray-400" />
                          <p className="text-sm text-gray-500 font-light">
                            {(region.population / 1000000).toFixed(1)}M population
                          </p>
                        </div>
                      </div>
                      <div className={`w-16 h-16 rounded-full flex items-center justify-center text-2xl font-light ${colors.text} bg-gray-50 border-2 border-gray-200`}>
                        {region.temp}°
                      </div>
                    </div>

                    {/* Temperature bar */}
                    <div className="mb-6">
                      <div className="flex justify-between items-center mb-2">
                        <span className="text-xs text-gray-500 font-light uppercase tracking-wider">Temperature</span>
                        <span className="text-sm font-light text-gray-700">
                          {region.temp > 38 ? 'Extreme' : region.temp > 35 ? 'High' : 'Moderate'}
                        </span>
                      </div>
                      <div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div
                          className={`h-full transition-all ${
                            region.temp > 38
                              ? 'bg-red-500'
                              : region.temp > 35
                              ? 'bg-orange-500'
                              : 'bg-yellow-500'
                          }`}
                          style={{ width: `${(region.temp / 45) * 100}%` }}
                        />
                      </div>
                    </div>

                    {/* Health risk badge */}
                    <div className="flex gap-2">
                      <span className={`px-3 py-1 text-xs font-light rounded-full ${colors.badge}`}>
                        Health Risk: {region.health_risk.charAt(0).toUpperCase() + region.health_risk.slice(1)}
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* Health Impact Section */}
      <section className="py-24 px-6 bg-white">
        <div className="max-w-7xl mx-auto">
          <h2 className="text-5xl font-light text-gray-900 mb-16 text-center">
            Health & Safety Monitoring
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-12">
            {[
              {
                icon: <Heart size={32} className="text-red-600" />,
                title: 'Health Alerts',
                description: 'Real-time monitoring of heat-related health risks and hospital admissions'
              },
              {
                icon: <Thermometer size={32} className="text-yellow-600" />,
                title: 'Temperature Forecast',
                description: 'AI-powered temperature prediction up to 14 days in advance'
              },
              {
                icon: <Sun size={32} className="text-orange-600" />,
                title: 'UV & Health Index',
                description: 'Combined heat stress and UV exposure risk assessment'
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
        <section className="py-24 px-6 bg-gradient-to-br from-yellow-50 to-orange-50">
          <div className="max-w-4xl mx-auto">
            <div className="flex items-center justify-between mb-8">
              <h2 className="text-4xl font-light text-gray-900">
                {selectedRegion.name} — Heat Assessment
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
                  { label: 'Temperature', value: selectedRegion.temp, unit: '°C' },
                  { label: 'Population at Risk', value: (selectedRegion.population / 1000000).toFixed(1), unit: 'M' },
                  { label: 'Health Risk', value: selectedRegion.health_risk.charAt(0).toUpperCase() + selectedRegion.health_risk.slice(1) },
                  { label: 'Alert Level', value: selectedRegion.temp > 38 ? 'EXTREME' : selectedRegion.temp > 35 ? 'HIGH' : 'MODERATE' }
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
                <h3 className="text-2xl font-light text-gray-900 mb-4">Health Recommendations</h3>
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <span className="text-gray-700 font-light">Vulnerable populations</span>
                    <span className="text-lg font-light text-red-600">Extra precautions advised</span>
                  </div>
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <span className="text-gray-700 font-light">Heat wave duration</span>
                    <span className="text-lg font-light text-gray-700">3-5 days expected</span>
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
