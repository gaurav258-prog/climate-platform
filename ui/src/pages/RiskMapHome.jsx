import { Waves, Flame, Thermometer, Activity } from 'lucide-react'

/**
 * Risk Map Landing Page
 * Shows all 4 hazard types with quick navigation
 */
export default function RiskMapHome({ onHazardSelect }) {
  const hazards = [
    {
      id: 'flood',
      name: 'Flood Risk',
      icon: Waves,
      description: 'Real-time flood risk assessment, hydrological forecasting, and early warning systems',
      color: 'from-blue-500 to-cyan-500',
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-200',
      stats: { active: '45+', regions: '15', avgRisk: '62%', population: '3.2M' }
    },
    {
      id: 'wildfire',
      name: 'Wildfire Risk',
      icon: Flame,
      description: 'Predictive wildfire risk mapping with satellite data, fire spread modeling, and emergency response coordination',
      color: 'from-orange-500 to-red-600',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-200',
      stats: { active: '60+', regions: '18', avgRisk: '71%', area: '2.1M km²' }
    },
    {
      id: 'heat',
      name: 'Heat Stress Risk',
      icon: Thermometer,
      description: 'Monitor extreme heat events, forecast health impacts, and coordinate emergency response for vulnerable populations',
      color: 'from-yellow-500 to-orange-600',
      bgColor: 'bg-yellow-50',
      borderColor: 'border-yellow-200',
      stats: { waves: '22+', regions: '12', avgRisk: '58%', population: '78M' }
    },
    {
      id: 'seismic',
      name: 'Seismic Risk',
      icon: Activity,
      description: 'Real-time earthquake risk forecasting, damage assessment, and aftershock prediction for Europe',
      color: 'from-red-500 to-orange-500',
      bgColor: 'bg-red-50',
      borderColor: 'border-red-200',
      stats: { events: '28+', regions: '8', avgRisk: '65%', population: '54M' }
    }
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-white">
      {/* Hero Section */}
      <section className="relative min-h-[40vh] flex items-center justify-center overflow-hidden pt-12 pb-12">
        <div className="text-center px-6 max-w-4xl mx-auto w-full">
          <h1 className="text-6xl md:text-7xl font-light text-gray-900 mb-6 leading-tight">
            Climate Risk
            <span className="block text-transparent bg-clip-text bg-gradient-to-r from-blue-500 via-purple-500 to-red-500">
              Intelligence
            </span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Monitor and forecast natural hazards in real-time with satellite data, AI models, and open-source climate science.
          </p>

          <p className="text-sm text-gray-500 font-light">
            Select a hazard type to explore risk assessments, regional breakdowns, and detailed analysis.
          </p>
        </div>
      </section>

      {/* Hazard Grid */}
      <section className="py-12 px-6 max-w-7xl mx-auto w-full">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {hazards.map((hazard) => {
            const Icon = hazard.icon
            return (
              <button
                key={hazard.id}
                onClick={() => onHazardSelect(hazard.id)}
                className={`${hazard.bgColor} ${hazard.borderColor} rounded-2xl border p-8 text-left hover:shadow-lg transition-all cursor-pointer`}
              >
                {/* Icon & Title */}
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h2 className="text-3xl font-semibold text-gray-900 mb-2">{hazard.name}</h2>
                  </div>
                  <div className={`p-3 rounded-lg bg-gradient-to-br ${hazard.color}`}>
                    <Icon size={32} className="text-white" />
                  </div>
                </div>

                {/* Description */}
                <p className="text-gray-700 leading-relaxed mb-6">
                  {hazard.description}
                </p>

                {/* Stats */}
                <div className="grid grid-cols-4 gap-3 pt-6 border-t border-gray-300">
                  {Object.entries(hazard.stats).map(([key, value]) => (
                    <div key={key} className="text-center">
                      <p className="text-sm text-gray-600 font-medium capitalize">{key}</p>
                      <p className="text-lg font-semibold text-gray-900 mt-1">{value}</p>
                    </div>
                  ))}
                </div>

                {/* CTA */}
                <div className="mt-6 pt-6 border-t border-gray-300">
                  <p className="text-sm font-semibold text-gray-900 hover:text-gray-700">
                    View Dashboard →
                  </p>
                </div>
              </button>
            )
          })}
        </div>
      </section>

      {/* Info Section */}
      <section className="py-12 px-6 max-w-7xl mx-auto w-full">
        <div className="bg-gray-50 rounded-2xl p-8 border border-gray-200">
          <h3 className="text-2xl font-semibold text-gray-900 mb-4">About These Assessments</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div>
              <h4 className="font-semibold text-gray-900 mb-2">Real-Time Data</h4>
              <p className="text-gray-600 text-sm leading-relaxed">
                Live data from satellite, weather stations, and seismic networks updated continuously.
              </p>
            </div>
            <div>
              <h4 className="font-semibold text-gray-900 mb-2">Predictive Models</h4>
              <p className="text-gray-600 text-sm leading-relaxed">
                AI-powered forecasting with statistical models validated against historical data.
              </p>
            </div>
            <div>
              <h4 className="font-semibold text-gray-900 mb-2">Open Source</h4>
              <p className="text-gray-600 text-sm leading-relaxed">
                Built on open datasets and transparent methodologies for climate intelligence.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer spacing */}
      <div className="h-12" />
    </div>
  )
}
