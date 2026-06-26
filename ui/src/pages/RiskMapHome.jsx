/**
 * Risk Map Landing Page - BCG Style
 * Simple, professional design with clickable hazard cards
 */
export default function RiskMapHome({ onHazardSelect }) {
  const hazards = [
    {
      id: 'flood',
      name: 'Flood Risk',
      icon: '💧',
      description: 'Real-time flood risk assessment, hydrological forecasting, and early warning systems',
      bgColor: 'bg-blue-50',
      borderColor: 'border-blue-300',
      accentColor: 'text-blue-600',
      stats: { active: '45+', regions: '15', avgRisk: '62%', population: '3.2M' }
    },
    {
      id: 'wildfire',
      name: 'Wildfire Risk',
      icon: '🔥',
      description: 'Predictive wildfire risk mapping with satellite data, fire spread modeling, and emergency response coordination',
      bgColor: 'bg-orange-50',
      borderColor: 'border-orange-300',
      accentColor: 'text-orange-600',
      stats: { active: '60+', regions: '18', avgRisk: '71%', area: '2.1M km²' }
    },
    {
      id: 'heat',
      name: 'Heat Stress Risk',
      icon: '☀️',
      description: 'Monitor extreme heat events, forecast health impacts, and coordinate emergency response for vulnerable populations',
      bgColor: 'bg-yellow-50',
      borderColor: 'border-yellow-300',
      accentColor: 'text-yellow-600',
      stats: { waves: '22+', regions: '12', avgRisk: '58%', population: '78M' }
    },
    {
      id: 'seismic',
      name: 'Seismic Risk',
      icon: '📍',
      description: 'Real-time earthquake risk forecasting, damage assessment, and aftershock prediction for Europe',
      bgColor: 'bg-red-50',
      borderColor: 'border-red-300',
      accentColor: 'text-red-600',
      stats: { events: '28+', regions: '8', avgRisk: '65%', population: '54M' }
    }
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Hero Section */}
      <section className="relative min-h-[40vh] flex items-center justify-center overflow-hidden pt-12 pb-12 bg-white">
        <div className="text-center px-6 max-w-4xl mx-auto w-full">
          <h1 className="text-6xl md:text-7xl font-light text-gray-900 mb-6 leading-tight">
            Climate
            <span className="block text-blue-600">Intelligence</span>
          </h1>

          <p className="text-xl text-gray-600 font-light mb-8 max-w-2xl mx-auto leading-relaxed">
            Monitor and forecast natural hazards with real-time data, predictive models, and professional risk assessments.
          </p>

          <p className="text-sm text-gray-500 font-light">
            Select a hazard type below to explore detailed risk maps, regional analysis, and forecasts.
          </p>
        </div>
      </section>

      {/* Hazard Grid */}
      <section className="py-12 px-6 max-w-7xl mx-auto w-full">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {hazards.map((hazard) => (
            <button
              key={hazard.id}
              onClick={() => onHazardSelect(hazard.id)}
              className={`${hazard.bgColor} ${hazard.borderColor} rounded-lg border-2 p-8 text-left hover:shadow-md hover:border-gray-400 transition-all cursor-pointer bg-white`}
            >
              {/* Icon & Title */}
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h2 className={`text-2xl font-semibold text-gray-900 mb-1`}>{hazard.name}</h2>
                </div>
                <div className={`text-4xl`}>{hazard.icon}</div>
              </div>

              {/* Description */}
              <p className="text-gray-700 text-sm leading-relaxed mb-6">
                {hazard.description}
              </p>

              {/* Stats */}
              <div className="grid grid-cols-4 gap-3 pt-6 border-t border-gray-200">
                {Object.entries(hazard.stats).map(([key, value]) => (
                  <div key={key} className="text-center">
                    <p className="text-xs text-gray-500 uppercase font-semibold">{key}</p>
                    <p className="text-sm font-semibold text-gray-900 mt-2">{value}</p>
                  </div>
                ))}
              </div>

              {/* CTA */}
              <div className="mt-6 pt-6 border-t border-gray-200">
                <p className={`text-sm font-semibold ${hazard.accentColor}`}>
                  View Dashboard →
                </p>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* Footer spacing */}
      <div className="h-12" />
    </div>
  )
}
